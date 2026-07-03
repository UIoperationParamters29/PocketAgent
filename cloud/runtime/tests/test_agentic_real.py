"""Real agentic test — actually converse with the agent and have it test
every tool, explore its workspace, and confirm it works like z.ai agentic mode.

This isn't a mocked test — it uses the real LLM endpoint and the real cloud
runtime. The agent doesn't know it's being tested; it just gets a multi-turn
conversation that exercises every capability.

Run:  python tests/test_agentic_real.py
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

TMP_WS = Path(tempfile.mkdtemp(prefix="pa_agentic_"))
os.environ["PA_WORKSPACE_ROOT"] = str(TMP_WS)
os.environ["PA_CHANNEL_SECRET"] = "agentic-secret"
os.environ["PA_HOST"] = "127.0.0.1"
os.environ["PA_PORT"] = "8801"

from app.config import settings  # noqa: E402

LLM_BASE_URL = os.environ.get("PA_TEST_LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("PA_TEST_LLM_API_KEY", "")
LLM_MODEL = os.environ.get("PA_TEST_LLM_MODEL", "")


async def main():
    if not LLM_BASE_URL or not LLM_API_KEY:
        print("Set PA_TEST_LLM_BASE_URL + PA_TEST_LLM_API_KEY + PA_TEST_LLM_MODEL")
        return 1

    print(f"=== Real Agentic Test ===")
    print(f"  base_url: {LLM_BASE_URL}")
    print(f"  model:    {LLM_MODEL}")
    print(f"  workspace: {TMP_WS}")
    print()

    # Seed a few files so the agent has something to explore
    (TMP_WS / "README.md").write_text("# Test Workspace\n\nThis is the agent's workspace.")
    (TMP_WS / "data").mkdir(exist_ok=True)
    (TMP_WS / "data" / "sales.csv").write_text("month,revenue\nJan,1000\nFeb,1500\nMar,1200\n")
    print("Seeded: README.md, data/sales.csv")
    print()

    # Start runtime
    import uvicorn
    config = uvicorn.Config("app.main:app", host=settings.host, port=settings.port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(1.5)

    ws_url = f"ws://{settings.host}:{settings.port}/agent"
    failures: list[str] = []
    tool_calls_seen: set[str] = set()

    try:
        async with websockets.connect(ws_url, max_size=2**22) as ws:
            await ws.send(json.dumps({
                "type": "session.start",
                "channel_secret": "agentic-secret",
                "session": {"base_url": LLM_BASE_URL, "api_key": LLM_API_KEY, "model": LLM_MODEL},
            }))
            start = json.loads(await ws.recv())
            assert start["type"] == "session.start"
            print(f"[ok] Connected; session_id={start['session_id']}")
            print()

            # ---- Conversation turns ----
            # Each turn is a real request that exercises a different capability.
            turns = [
                (
                    "Test 1: Workspace exploration",
                    "What's in your workspace? Use the LS tool on '.' and tell me what you find. Then read README.md and summarize it in one sentence.",
                    ["LS", "Read"],
                ),
                (
                    "Test 2: File creation",
                    "Create a new file at scripts/hello.py with content: print('hello from PocketAgent')\nThen run it with Bash and tell me the output.",
                    ["Write", "Bash"],
                ),
                (
                    "Test 3: File editing",
                    "Edit scripts/hello.py to also print 'and goodbye' on a second line. Then run it again and tell me the new output.",
                    ["Edit", "Bash"],
                ),
                (
                    "Test 4: Searching",
                    "Use Grep to search the workspace for the word 'revenue'. Tell me which file(s) and lines contain it.",
                    ["Grep"],
                ),
                (
                    "Test 5: Globbing",
                    "Use Glob to find all .py files in the workspace. List them.",
                    ["Glob"],
                ),
                (
                    "Test 6: TodoWrite",
                    "Create a todo list with 3 items: 'explore workspace' (completed), 'write script' (completed), 'report findings' (in_progress).",
                    ["TodoWrite"],
                ),
                (
                    "Test 7: Skill discovery",
                    "Use the Skill tool with mode='list' to see what skills are installed. Tell me what's available.",
                    ["Skill"],
                ),
                (
                    "Test 8: Multi-step task",
                    "Read data/sales.csv, calculate the average revenue using Bash (python -c is fine), and write the result to a new file called avg.txt. Then confirm by reading avg.txt back.",
                    # The agent may use Write OR Bash (via shell redirect/python) to create avg.txt — both are valid.
                    # We just need Read (the CSV) and Bash (the calculation). Disk verification checks the file exists.
                    ["Read", "Bash"],
                ),
                (
                    "Test 9: Workspace summary",
                    "Give me a final summary: list every file currently in your workspace using LS, and confirm you can use all the tools (Bash, Read, Write, Edit, Glob, Grep, LS, TodoWrite, Skill).",
                    ["LS"],
                ),
            ]

            for label, prompt, expected_tools in turns:
                print(f"--- {label} ---")
                print(f"  User: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
                await ws.send(json.dumps({"type": "user.message", "content": prompt}))
                events = await _drain_until(ws, "session.end", timeout=180)
                types = [e["type"] for e in events]
                tools_used = [e["name"] for e in events if e["type"] == "tool.call"]
                for t in tools_used:
                    tool_calls_seen.add(t)

                # Show the agent's final message
                final_msgs = [e for e in events if e["type"] == "assistant.message"]
                if final_msgs:
                    content = final_msgs[-1]["content"]
                    print(f"  Agent: {content[:300]}{'...' if len(content) > 300 else ''}")
                else:
                    print(f"  ⚠️  No assistant.message — events: {types}")

                # Verify expected tools were called
                missing = [t for t in expected_tools if t not in tools_used]
                if missing:
                    failures.append(f"{label}: expected tools {missing} but agent only called {tools_used}")
                    print(f"  ❌ Missing tools: {missing}")
                else:
                    print(f"  ✅ Tools used: {tools_used}")
                print()

            # ---- Final verification: check files on disk ----
            print("--- Disk verification ---")
            # The agent may save deliverables to download/ (z.ai convention) OR to root.
            expected_files = [
                ("README.md", TMP_WS / "README.md"),
                ("data/sales.csv", TMP_WS / "data/sales.csv"),
                ("scripts/hello.py", TMP_WS / "scripts/hello.py"),
                ("avg.txt (root or download/)", TMP_WS / "avg.txt" if (TMP_WS / "avg.txt").exists() else TMP_WS / "download/avg.txt"),
            ]
            avg_path = None
            for label, p in expected_files:
                if p.exists():
                    size = p.stat().st_size
                    print(f"  ✅ {label} ({size} bytes)")
                    if "avg.txt" in label:
                        avg_path = p
                else:
                    failures.append(f"File not created on disk: {label}")
                    print(f"  ❌ {label} missing")

            # Verify hello.py runs
            import subprocess
            r = subprocess.run(["python3", str(TMP_WS / "scripts/hello.py")], capture_output=True, text=True, timeout=5)
            if "hello from PocketAgent" in r.stdout and "goodbye" in r.stdout:
                print(f"  ✅ scripts/hello.py runs correctly: {r.stdout.strip()!r}")
            else:
                failures.append(f"hello.py output wrong: {r.stdout!r}")
                print(f"  ❌ hello.py output: {r.stdout!r}")

            # Verify avg.txt has a number
            if avg_path:
                avg = avg_path.read_text()
                # Extract the first number from the text
                import re
                nums = re.findall(r'[\d.]+', avg)
                if nums:
                    try:
                        val = float(nums[0])
                        if 1000 < val < 1500:  # avg of 1000, 1500, 1200 = 1233.33
                            print(f"  ✅ avg.txt has correct value: {val} (from {avg_path.name})")
                        else:
                            failures.append(f"avg.txt value out of expected range: {val}")
                            print(f"  ❌ avg.txt value: {val}")
                    except Exception as e:
                        failures.append(f"avg.txt not parseable: {avg!r} ({e})")
                        print(f"  ❌ avg.txt: {avg!r}")
                else:
                    failures.append(f"avg.txt has no number: {avg!r}")
                    print(f"  ❌ avg.txt: {avg!r}")

    finally:
        server.should_exit = True
        await asyncio.sleep(0.5)
        server_task.cancel()
        try: await server_task
        except asyncio.CancelledError: pass

    print()
    print("=" * 60)
    print(f"Tools exercised across all turns: {sorted(tool_calls_seen)}")
    expected_all = {"Bash", "Read", "Write", "Edit", "Glob", "Grep", "LS", "TodoWrite", "Skill"}
    missing_tools = expected_all - tool_calls_seen
    if missing_tools:
        failures.append(f"Never exercised: {missing_tools}")

    print()
    if failures:
        print(f"❌ AGENTIC TEST FAILED — {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    else:
        print("✅ AGENTIC TEST PASSED — agent explored workspace, used every tool,")
        print("   created files, ran scripts, searched content, made todos, discovered skills.")
        print("   This is z.ai agentic-mode parity.")
        return 0


async def _drain_until(ws, target_type: str, timeout: float = 60) -> list[dict]:
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
                print(f"  [error] {evt.get('message')}")
                break
        except asyncio.TimeoutError:
            break
    return events


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
