"""Smoke test for the PocketAgent runtime — verifies the tool surface and
the agent loop with a mocked LLM (no real API key needed).

Run:  cd cloud/runtime && python -m pytest tests/test_smoke.py -v
Or:   python tests/test_smoke.py    (standalone)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Allow running from anywhere
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use a temp workspace so we don't pollute the real one
import tempfile
TMP_WS = Path(tempfile.mkdtemp(prefix="pa_test_"))
os.environ["PA_WORKSPACE_ROOT"] = str(TMP_WS)
os.environ["PA_CHANNEL_SECRET"] = "test-secret"
os.environ["PA_DEFAULT_API_KEY"] = "test-key"

from app.config import settings  # noqa: E402
from app.tools import TOOLS, call_tool, to_openai_tools  # noqa: E402
from app.tools.registry import _resolve_safe  # noqa: E402
from app.agent import Session, run_agent_loop  # noqa: E402


def test_workspace_layout():
    """Workspace must have the z.ai-parity subdirs."""
    for sub in ("download", "scripts", "upload", "skills"):
        assert (settings.workspace_root / sub).exists(), f"missing {sub}/"
    print("[ok] workspace layout:", settings.workspace_root)


def test_path_sandbox():
    """_resolve_safe must reject escapes."""
    ok = _resolve_safe("foo.txt")
    assert ok == (settings.workspace_root / "foo.txt").resolve()
    try:
        _resolve_safe("../../etc/passwd")
        raise AssertionError("escape not blocked")
    except PermissionError:
        pass
    print("[ok] path sandbox blocks escapes")


async def test_tools():
    """Exercise each tool end-to-end."""
    # Write
    r = await call_tool("Write", {"file_path": "hello.txt", "content": "hello world\nfoo bar\n"})
    assert r.ok, r.error
    # Read
    r = await call_tool("Read", {"file_path": "hello.txt"})
    assert r.ok and "hello world" in r.output, r.output
    # Edit
    r = await call_tool("Edit", {"file_path": "hello.txt", "old_str": "foo bar", "new_str": "baz qux"})
    assert r.ok, r.error
    # Glob
    r = await call_tool("Glob", {"pattern": "*.txt"})
    assert r.ok and "hello.txt" in r.output, r.output
    # Grep
    r = await call_tool("Grep", {"pattern": "baz"})
    assert r.ok and "baz" in r.output, r.output
    # LS
    r = await call_tool("LS", {"path": "."})
    assert r.ok and "hello.txt" in r.output, r.output
    # Bash
    r = await call_tool("Bash", {"command": "echo $(date)"})
    assert r.ok and r.output.strip(), r.output
    # TodoWrite
    r = await call_tool("TodoWrite", {"todos": [{"id": "1", "content": "test", "status": "completed", "priority": "high"}]})
    assert r.ok, r.error
    print("[ok] all 8 tools work")


def test_openai_tools_schema():
    """to_openai_tools must produce valid OpenAI function-tool schema."""
    tools = to_openai_tools()
    assert len(tools) == 8, f"expected 8 tools, got {len(tools)}"
    for t in tools:
        assert t["type"] == "function"
        f = t["function"]
        assert f["name"] in TOOLS
        assert "description" in f and f["description"]
        assert "parameters" in f
    print("[ok] openai tools schema valid:", [t["function"]["name"] for t in tools])


async def test_agent_loop_mocked():
    """Run the agent loop with a fake LLM that issues one tool call, then ends.

    We monkey-patch the AsyncOpenAI client to return a deterministic stream.
    """
    from app.agent import _client  # noqa
    from openai.types.chat import ChatCompletionChunk
    from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta, ChoiceDeltaToolCall

    class FakeStream:
        def __init__(self, items):
            self._items = items
        def __aiter__(self):
            self._i = 0
            return self
        async def __anext__(self):
            if self._i >= len(self._items):
                raise StopAsyncIteration
            v = self._items[self._i]
            self._i += 1
            return v

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(*, model, messages, tools, tool_choice, stream):
                    # First call: ask to read a file
                    if not any(m.get("role") == "tool" for m in messages):
                        return FakeStream([
                            ChatCompletionChunk(
                                id="fake1", created=0, model=model, object="chat.completion.chunk", choices=[
                                    Choice(index=0, finish_reason="tool_calls", delta=ChoiceDelta(
                                        tool_calls=[ChoiceDeltaToolCall(
                                            index=0, id="call_1", type="function",
                                            function={"name": "Write", "arguments": json.dumps({"file_path": "out.txt", "content": "done"})}
                                        )]
                                    ))
                                ]
                            )
                        ])
                    # Second call: just say done
                    return FakeStream([
                        ChatCompletionChunk(id="fake2", created=0, model=model, object="chat.completion.chunk", choices=[
                            Choice(index=0, finish_reason="stop", delta=ChoiceDelta(content="Done!"))
                        ])
                    ])

    # Patch
    import app.agent as agent_mod
    orig_client = agent_mod._client
    agent_mod._client = lambda s: FakeClient()

    try:
        s = Session(api_key="fake", model="fake-model")
        events = []
        async for evt in run_agent_loop(s, "write 'done' to out.txt"):
            events.append(evt)

        types = [e["type"] for e in events]
        assert "user.message" in types
        assert "tool.call" in types
        assert "tool.result" in types
        assert "assistant.message" in types
        assert "session.end" in types
        # Verify the file was actually written
        assert (settings.workspace_root / "out.txt").read_text() == "done"
        print("[ok] agent loop ran end-to-end with mocked LLM")
        print("     events:", types)
    finally:
        agent_mod._client = orig_client


async def main():
    test_workspace_layout()
    test_path_sandbox()
    test_openai_tools_schema()
    await test_tools()
    await test_agent_loop_mocked()
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
