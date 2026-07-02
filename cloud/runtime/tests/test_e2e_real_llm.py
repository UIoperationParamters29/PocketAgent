"""End-to-end test against the real LLM endpoint + real cloud runtime.

This is the test that catches bugs the unit tests miss: actual LLM streaming,
tool-call execution, and the full event protocol. Runs the runtime locally
(on a random port) and connects via WebSocket.

Set the env vars before running:
  PA_TEST_LLM_BASE_URL=https://api.gateway.orgn.com/v1
  PA_TEST_LLM_API_KEY=sk-...
  PA_TEST_LLM_MODEL=near_glm_5  (or whichever)

Run:  python tests/test_e2e_real_llm.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use a temp workspace so we don't pollute the real one
TMP_WS = Path(tempfile.mkdtemp(prefix="pa_e2e_"))
os.environ["PA_WORKSPACE_ROOT"] = str(TMP_WS)
os.environ["PA_CHANNEL_SECRET"] = "e2e-secret"
os.environ["PA_HOST"] = "127.0.0.1"
os.environ["PA_PORT"] = "8799"

from app.config import settings  # noqa: E402

LLM_BASE_URL = os.environ.get("PA_TEST_LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("PA_TEST_LLM_API_KEY", "")
LLM_MODEL = os.environ.get("PA_TEST_LLM_MODEL", "gpt-4o-mini")


async def main():
    if not LLM_BASE_URL or not LLM_API_KEY:
        print("Skipping — set PA_TEST_LLM_BASE_URL + PA_TEST_LLM_API_KEY to run this test.")
        return 0

    print(f"=== E2E test against real LLM ===")
    print(f"  base_url: {LLM_BASE_URL}")
    print(f"  model:    {LLM_MODEL}")
    print(f"  workspace: {TMP_WS}")
    print()

    # Start the runtime
    import uvicorn
    config = uvicorn.Config("app.main:app", host=settings.host, port=settings.port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(1.5)

    base = f"http://{settings.host}:{settings.port}"
    ws_url = f"ws://{settings.host}:{settings.port}/agent"

    failures: list[str] = []

    try:
        # ---- Test 1: health endpoint ----
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{base}/")
            assert r.status_code == 200
            data = r.json()
            assert data["name"] == "PocketAgent Runtime"
            print(f"[ok] GET / -> {data['name']} v{data['version']}")

        # ---- Test 2: WS handshake + session.start ----
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({
                "type": "session.start",
                "channel_secret": "e2e-secret",
                "session": {
                    "base_url": LLM_BASE_URL,
                    "api_key": LLM_API_KEY,
                    "model": LLM_MODEL,
                },
            }))
            start = json.loads(await ws.recv())
            assert start["type"] == "session.start", f"expected session.start, got {start}"
            session_id = start["session_id"]
            print(f"[ok] WS handshake; session_id={session_id}")

            # ---- Test 3: simple greeting (no tools expected) ----
            print()
            print("--- Test 3: simple greeting ---")
            await ws.send(json.dumps({"type": "user.message", "content": "Reply with exactly: PONG"}))
            events = await _drain_until(ws, "session.end", timeout=90)
            types = [e["type"] for e in events]
            print(f"  events: {types}")
            final_msgs = [e for e in events if e["type"] == "assistant.message"]
            if not final_msgs:
                # Maybe it's still streaming — collect all assistant.delta
                deltas = "".join(e["content"] for e in events if e["type"] == "assistant.delta")
                if deltas:
                    print(f"  (no assistant.message; deltas only): {deltas[:200]!r}")
                    # This is a real bug — log it
                    failures.append("LLM streamed deltas but never sent assistant.message (likely a finish_reason or content-vs-reasoning_content issue)")
                else:
                    failures.append("No assistant.message and no assistant.delta events — LLM produced no output")
            else:
                content = final_msgs[0]["content"]
                print(f"  reply: {content!r}")
                if "PONG" not in content.upper():
                    failures.append(f"Expected 'PONG' in reply, got {content!r}")

            # ---- Test 4: tool call (Bash) ----
            print()
            print("--- Test 4: tool call (Bash echo) ---")
            await ws.send(json.dumps({"type": "user.message", "content": "Use the Bash tool to run: echo hello-from-e2e-test. Then tell me what it printed."}))
            events = await _drain_until(ws, "session.end", timeout=120)
            types = [e["type"] for e in events]
            print(f"  events: {types}")
            tool_calls = [e for e in events if e["type"] == "tool.call"]
            tool_results = [e for e in events if e["type"] == "tool.result"]
            if not tool_calls:
                failures.append("LLM did not call any tool (expected Bash)")
            else:
                print(f"  tool called: {tool_calls[0]['name']} with args {tool_calls[0]['args']}")
                if not tool_results:
                    failures.append("Tool was called but no tool.result event arrived")
                else:
                    output = tool_results[0]["output"]
                    print(f"  tool result: {output[:200]!r}")
                    if "hello-from-e2e-test" not in output:
                        failures.append(f"Tool output didn't contain expected string: {output!r}")

            # ---- Test 5: file write (Write tool) ----
            print()
            print("--- Test 5: file write ---")
            await ws.send(json.dumps({"type": "user.message", "content": "Use the Write tool to create a file at e2e_test.txt with the content 'e2e was here'. Then confirm."}))
            events = await _drain_until(ws, "session.end", timeout=120)
            types = [e["type"] for e in events]
            print(f"  events: {types}")
            # Verify the file exists on disk
            test_file = TMP_WS / "e2e_test.txt"
            if test_file.exists():
                content = test_file.read_text()
                print(f"  file content: {content!r}")
                if "e2e was here" not in content:
                    failures.append(f"File content mismatch: {content!r}")
            else:
                failures.append("Write tool didn't create the file on disk")

            # ---- Test 6: TodoWrite ----
            print()
            print("--- Test 6: TodoWrite ---")
            await ws.send(json.dumps({"type": "user.message", "content": "Use the TodoWrite tool to create a 2-item todo list: 'step 1' (pending) and 'step 2' (completed). Then say done."}))
            events = await _drain_until(ws, "session.end", timeout=120)
            todo_updates = [e for e in events if e["type"] == "todo.update"]
            if not todo_updates:
                failures.append("No todo.update event — TodoWrite wasn't called")
            else:
                todos = todo_updates[0]["todos"]
                print(f"  todos: {len(todos)} items")
                if len(todos) != 2:
                    failures.append(f"Expected 2 todos, got {len(todos)}")

            # ---- Test 7: workspace file listing ----
            print()
            print("--- Test 7: workspace /workspace endpoint ---")
            async with httpx.AsyncClient() as c:
                r = await c.get(f"{base}/workspace?depth=2")
                tree = r.json()
                # Walk the tree looking for e2e_test.txt
                found = _find_in_tree(tree, "e2e_test.txt")
                if found:
                    print(f"  [ok] e2e_test.txt visible in workspace tree")
                else:
                    failures.append("e2e_test.txt not visible in /workspace tree")

    finally:
        server.should_exit = True
        await asyncio.sleep(0.5)
        server_task.cancel()
        try: await server_task
        except asyncio.CancelledError: pass

    print()
    print("=" * 60)
    if failures:
        print(f"❌ E2E test FAILED — {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    else:
        print("✅ E2E test PASSED — all 7 checks green")
        return 0


async def _drain_until(ws, target_type: str, timeout: float = 60) -> list[dict]:
    """Receive events until we see one of target_type or timeout."""
    events = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.time())
            evt = json.loads(raw)
            events.append(evt)
            if evt.get("type") == target_type:
                break
            if evt.get("type") == "error":
                print(f"  [error event] {evt.get('message')}")
                break
        except asyncio.TimeoutError:
            break
    return events


def _find_in_tree(node: dict, name: str) -> bool:
    if node.get("name") == name:
        return True
    for child in node.get("children", []):
        if _find_in_tree(child, name):
            return True
    return False


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
