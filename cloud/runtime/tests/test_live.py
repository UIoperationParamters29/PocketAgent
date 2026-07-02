"""Live integration test: start the runtime, hit /, hit /workspace, and run
a full WS session with a mocked LLM. Tests the bidirectional AskUserQuestion
flow end-to-end. No real API key needed.

Run:  python tests/test_live.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP_WS = Path(tempfile.mkdtemp(prefix="pa_live_"))
os.environ["PA_WORKSPACE_ROOT"] = str(TMP_WS)
os.environ["PA_CHANNEL_SECRET"] = "live-secret"
os.environ["PA_DEFAULT_API_KEY"] = "test-key"
os.environ["PA_HOST"] = "127.0.0.1"
os.environ["PA_PORT"] = "8765"

from app.config import settings  # noqa: E402


async def main():
    import uvicorn
    config = uvicorn.Config("app.main:app", host=settings.host, port=settings.port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(1.5)

    base = f"http://{settings.host}:{settings.port}"

    try:
        # 1. GET /
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{base}/")
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["name"] == "PocketAgent Runtime"
            print("[ok] GET / ->", data["name"], data["version"])

        # 2. GET /workspace
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{base}/workspace")
            assert r.status_code == 200, r.text
            data = r.json()
            assert "children" in data
            print("[ok] GET /workspace ->", [c["name"] for c in data.get("children", [])])

        # 3. WS handshake with bad secret
        async with websockets.connect(f"ws://{settings.host}:{settings.port}/agent") as ws:
            await ws.send(json.dumps({"type": "session.start", "channel_secret": "WRONG", "session": {"api_key": "x"}}))
            reply = json.loads(await ws.recv())
            assert reply["type"] == "error" and reply["kind"] == "auth", reply
            print("[ok] bad secret rejected:", reply["message"])

        # 4. WS handshake with no api_key
        async with websockets.connect(f"ws://{settings.host}:{settings.port}/agent") as ws:
            await ws.send(json.dumps({"type": "session.start", "channel_secret": "live-secret", "session": {}}))
            reply = json.loads(await ws.recv())
            assert reply["type"] == "error" and reply["kind"] == "config", reply
            print("[ok] missing api_key rejected:", reply["message"])

        # 5. Full mocked session: Bash tool
        from openai.types.chat import ChatCompletionChunk
        from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta, ChoiceDeltaToolCall

        class FakeStream:
            def __init__(self, items): self._items = items
            def __aiter__(self): self._i = 0; return self
            async def __anext__(self):
                if self._i >= len(self._items): raise StopAsyncIteration
                v = self._items[self._i]; self._i += 1; return v

        # A fake client that supports a "mode" that toggles between bash and ask_user
        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    async def create(*, model, messages, tools, tool_choice, stream):
                        # AskUserQuestion mode: first call asks, second call (after answer) responds
                        if any("ask_user" in (m.get("content") or "").lower() for m in messages if m.get("role") == "user"):
                            if not any(m.get("role") == "tool" for m in messages):
                                return FakeStream([ChatCompletionChunk(
                                    id="a1", created=0, model=model, object="chat.completion.chunk",
                                    choices=[Choice(index=0, finish_reason="tool_calls", delta=ChoiceDelta(
                                        tool_calls=[ChoiceDeltaToolCall(index=0, id="a1", type="function",
                                            function={"name": "AskUserQuestion", "arguments": json.dumps({
                                                "questions": [{"question": "Tone?", "header": "Tone", "type": "single",
                                                    "options": [{"label": "Casual", "description": "x"}, {"label": "Formal", "description": "y"}]}]
                                            })})]
                                    ))]
                                )])
                            return FakeStream([ChatCompletionChunk(
                                id="a2", created=0, model=model, object="chat.completion.chunk",
                                choices=[Choice(index=0, finish_reason="stop", delta=ChoiceDelta(content="Got it, going casual."))]
                            )])
                        # Default bash mode
                        if not any(m.get("role") == "tool" for m in messages):
                            return FakeStream([ChatCompletionChunk(
                                id="f1", created=0, model=model, object="chat.completion.chunk",
                                choices=[Choice(index=0, finish_reason="tool_calls", delta=ChoiceDelta(
                                    tool_calls=[ChoiceDeltaToolCall(index=0, id="c1", type="function",
                                        function={"name": "Bash", "arguments": json.dumps({"command": "echo hello-from-bash"})})]
                                ))]
                            )])
                        return FakeStream([ChatCompletionChunk(
                            id="f2", created=0, model=model, object="chat.completion.chunk",
                            choices=[Choice(index=0, finish_reason="stop", delta=ChoiceDelta(content="All done!"))]
                        )])

        import app.agent as agent_mod
        agent_mod._client = lambda s: FakeClient()

        # 5a. Bash session
        async with websockets.connect(f"ws://{settings.host}:{settings.port}/agent") as ws:
            await ws.send(json.dumps({
                "type": "session.start",
                "channel_secret": "live-secret",
                "session": {"api_key": "test", "model": "fake", "base_url": "https://example.com/v1"},
            }))
            start = json.loads(await ws.recv())
            assert start["type"] == "session.start", start
            print("[ok] WS handshake; session_id =", start["session_id"])

            await ws.send(json.dumps({"type": "user.message", "content": "run echo hello-from-bash"}))
            events = []
            try:
                while True:
                    evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                    events.append(evt)
                    if evt["type"] == "session.end":
                        break
            except asyncio.TimeoutError:
                pass

            types = [e["type"] for e in events]
            print("[ok] bash session events:", types)
            assert "tool.call" in types and "tool.result" in types and "session.end" in types, types
            tool_results = [e for e in events if e["type"] == "tool.result"]
            assert any("hello-from-bash" in e["output"] for e in tool_results), tool_results
            print("[ok] bash output streamed to client:", tool_results[0]["output"].strip())

        # 6. AskUserQuestion bidirectional flow
        async with websockets.connect(f"ws://{settings.host}:{settings.port}/agent") as ws:
            await ws.send(json.dumps({
                "type": "session.start",
                "channel_secret": "live-secret",
                "session": {"api_key": "test", "model": "fake", "base_url": "https://example.com/v1"},
            }))
            start = json.loads(await ws.recv())
            assert start["type"] == "session.start", start
            print("[ok] WS handshake for AskUserQuestion test; session_id =", start["session_id"])

            await ws.send(json.dumps({"type": "user.message", "content": "ask_user: which tone?"}))
            events = []
            question_id = None
            try:
                while True:
                    evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                    events.append(evt)
                    if evt["type"] == "user.question":
                        question_id = evt["question_id"]
                        # Schedule the answer asynchronously
                        asyncio.create_task(_send_answer(ws, question_id))
                    if evt["type"] == "session.end":
                        break
            except asyncio.TimeoutError:
                pass

            types = [e["type"] for e in events]
            print("[ok] ask-user session events:", types)
            assert "user.question" in types, types
            assert question_id, "no question_id received"
            assert "tool.result" in types, types  # the AskUserQuestion tool should have returned
            # Verify the answer reached the LLM context (final message should mention casual)
            final_msgs = [e for e in events if e["type"] == "assistant.message"]
            assert any("casual" in (e.get("content") or "").lower() for e in final_msgs), final_msgs
            print("[ok] AskUserQuestion: agent asked, phone answered, agent resumed")

        print("\n=== LIVE INTEGRATION TEST PASSED ===")
    finally:
        server.should_exit = True
        await asyncio.sleep(0.5)
        server_task.cancel()
        try: await server_task
        except asyncio.CancelledError: pass


async def _send_answer(ws, question_id: str):
    """Simulate the phone answering a user.question after a short delay."""
    await asyncio.sleep(0.2)
    await ws.send(json.dumps({
        "type": "user.answer",
        "question_id": question_id,
        "answer": [{"header": "Tone", "answer": "casual"}],
    }))


if __name__ == "__main__":
    asyncio.run(main())
