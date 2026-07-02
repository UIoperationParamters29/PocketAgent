"""Smoke test for the PocketAgent runtime — verifies the tool surface and
the agent loop with a mocked LLM (no real API key needed).

Run:  cd cloud/runtime && python tests/test_smoke.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP_WS = Path(tempfile.mkdtemp(prefix="pa_test_"))
os.environ["PA_WORKSPACE_ROOT"] = str(TMP_WS)
os.environ["PA_CHANNEL_SECRET"] = "test-secret"
os.environ["PA_DEFAULT_API_KEY"] = "test-key"

from app.config import settings  # noqa: E402
from app.tools import TOOLS, call_tool, to_openai_tools  # noqa: E402
from app.tools.registry import _resolve_safe  # noqa: E402
from app.tools import ToolContext  # noqa: E402
from app.agent import Session, UserResponder, run_agent_loop  # noqa: E402


def make_ctx(**kw) -> ToolContext:
    """Build a ToolContext for testing (default session + responder)."""
    s = Session(api_key="test", model="test-model")
    return ToolContext(session=s, responder=kw.get("responder"), depth=kw.get("depth", 0))


def test_workspace_layout():
    for sub in ("download", "scripts", "upload", "skills"):
        assert (settings.workspace_root / sub).exists(), f"missing {sub}/"
    print("[ok] workspace layout:", settings.workspace_root)


def test_path_sandbox():
    ok = _resolve_safe("foo.txt")
    assert ok == (settings.workspace_root / "foo.txt").resolve()
    try:
        _resolve_safe("../../etc/passwd")
        raise AssertionError("escape not blocked")
    except PermissionError:
        pass
    print("[ok] path sandbox blocks escapes")


def test_openai_tools_schema():
    tools = to_openai_tools()
    assert len(tools) == 13, f"expected 13 tools, got {len(tools)}"
    for t in tools:
        assert t["type"] == "function"
        f = t["function"]
        assert f["name"] in TOOLS
        assert "description" in f and f["description"]
        assert "parameters" in f
    print("[ok] openai tools schema valid:", [t["function"]["name"] for t in tools])


async def test_core_tools():
    """Exercise the 8 core tools end-to-end."""
    ctx = make_ctx()
    r = await call_tool("Write", {"file_path": "hello.txt", "content": "hello world\nfoo bar\n"}, ctx)
    assert r.ok, r.error
    r = await call_tool("Read", {"file_path": "hello.txt"}, ctx)
    assert r.ok and "hello world" in r.output, r.output
    r = await call_tool("Edit", {"file_path": "hello.txt", "old_str": "foo bar", "new_str": "baz qux"}, ctx)
    assert r.ok, r.error
    r = await call_tool("Glob", {"pattern": "*.txt"}, ctx)
    assert r.ok and "hello.txt" in r.output, r.output
    r = await call_tool("Grep", {"pattern": "baz"}, ctx)
    assert r.ok and "baz" in r.output, r.output
    r = await call_tool("LS", {"path": "."}, ctx)
    assert r.ok and "hello.txt" in r.output, r.output
    r = await call_tool("Bash", {"command": "echo $(date)"}, ctx)
    assert r.ok and r.output.strip(), r.output
    r = await call_tool("TodoWrite", {"todos": [{"id": "1", "content": "test", "status": "completed", "priority": "high"}]}, ctx)
    assert r.ok, r.error
    print("[ok] all 8 core tools work")


async def test_skill_tool():
    """Skill tool should load a SKILL.md from workspace/skills/."""
    ctx = make_ctx()
    # Make a test skill
    skill_dir = settings.workspace_root / "skills" / "test-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: test-skill\n---\n# Test Skill\nHello world.")
    (skill_dir / "briefs").mkdir(exist_ok=True)
    (skill_dir / "briefs" / "test.md").write_text("test brief")

    r = await call_tool("Skill", {"name": "test-skill"}, ctx)
    assert r.ok, r.error
    assert "Test Skill" in r.output, r.output
    assert "briefs" in r.output, r.output

    # Missing skill returns helpful list
    r = await call_tool("Skill", {"name": "nope"}, ctx)
    assert not r.ok
    assert "test-skill" in r.output, r.output
    print("[ok] Skill tool loads SKILL.md + lists available")


async def test_outline_and_complete_tools():
    """Outline and Complete should emit events via the responder."""
    events = []

    class TestResponder(UserResponder):
        async def send_event(self, evt):
            events.append(evt)

    r = TestResponder()
    ctx = make_ctx(responder=r)

    out = await call_tool("Outline", {
        "document_type": "pdf",
        "sections": [{"index": 1, "title": "Intro", "task_brief": "First section"}],
        "design": {"style_name": "Swiss"},
    }, ctx)
    assert out.ok, out.error
    assert any(e["type"] == "outline.update" for e in events), events
    assert events[-1]["document_type"] == "pdf"

    comp = await call_tool("Complete", {
        "project_type": "document",
        "summary": "Made a thing.",
    }, ctx)
    assert comp.ok, comp.error
    assert any(e["type"] == "session.complete" for e in events), events
    assert events[-1]["project_type"] == "document"
    print("[ok] Outline + Complete emit events")


async def test_ask_user_question_tool():
    """AskUserQuestion should block on responder.ask, then return the answer."""
    class TestResponder(UserResponder):
        def __init__(self):
            super().__init__()
            self.events = []
        async def send_event(self, evt):
            self.events.append(evt)

    r = TestResponder()
    ctx = make_ctx(responder=r)

    # Schedule the resolution 100ms after the question is asked
    async def resolver():
        await asyncio.sleep(0.2)
        # Find the question_id from emitted events
        qid = None
        for e in r.events:
            if e.get("type") == "user.question":
                qid = e.get("question_id")
                break
        assert qid, "no user.question event emitted"
        r.resolve(qid, [{"header": "Tone", "answer": "casual"}])

    asyncio.create_task(resolver())
    result = await call_tool("AskUserQuestion", {
        "questions": [{"question": "Tone?", "header": "Tone", "type": "single", "options": [{"label": "Casual", "description": "x"}, {"label": "Formal", "description": "y"}]}],
    }, ctx)
    assert result.ok, result.error
    parsed = json.loads(result.output)
    assert parsed[0]["answer"] == "casual"
    print("[ok] AskUserQuestion blocks + resolves correctly")


async def test_agent_loop_mocked():
    """Run the agent loop with a fake LLM that issues one tool call, then ends."""
    from openai.types.chat import ChatCompletionChunk
    from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta, ChoiceDeltaToolCall

    class FakeStream:
        def __init__(self, items): self._items = items
        def __aiter__(self): self._i = 0; return self
        async def __anext__(self):
            if self._i >= len(self._items): raise StopAsyncIteration
            v = self._items[self._i]; self._i += 1; return v

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(*, model, messages, tools, tool_choice, stream):
                    if not any(m.get("role") == "tool" for m in messages):
                        return FakeStream([ChatCompletionChunk(
                            id="f1", created=0, model=model, object="chat.completion.chunk",
                            choices=[Choice(index=0, finish_reason="tool_calls", delta=ChoiceDelta(
                                tool_calls=[ChoiceDeltaToolCall(index=0, id="c1", type="function",
                                    function={"name": "Write", "arguments": json.dumps({"file_path": "out.txt", "content": "done"})})]
                            ))]
                        )])
                    return FakeStream([ChatCompletionChunk(
                        id="f2", created=0, model=model, object="chat.completion.chunk",
                        choices=[Choice(index=0, finish_reason="stop", delta=ChoiceDelta(content="Done!"))]
                    )])

    import app.agent as agent_mod
    orig = agent_mod._client
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
        assert (settings.workspace_root / "out.txt").read_text() == "done"
        print("[ok] agent loop ran end-to-end with mocked LLM")
        print("     events:", types)
    finally:
        agent_mod._client = orig


async def test_subagent_tool_mocked():
    """Task tool spawns a subagent that runs to completion and returns text."""
    from openai.types.chat import ChatCompletionChunk
    from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta

    class FakeStream:
        def __init__(self, items): self._items = items
        def __aiter__(self): self._i = 0; return self
        async def __anext__(self):
            if self._i >= len(self._items): raise StopAsyncIteration
            v = self._items[self._i]; self._i += 1; return v

    # Parent: call Task. Subagent: just say "subagent result".
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(*, model, messages, tools, tool_choice, stream):
                    # Subagent: system prompt starts with "You are a PocketAgent subagent"
                    is_sub = any(
                        (m.get("content") or "").startswith("You are a PocketAgent subagent")
                        for m in messages if m.get("role") == "system"
                    )
                    if is_sub:
                        return FakeStream([ChatCompletionChunk(
                            id="s1", created=0, model=model, object="chat.completion.chunk",
                            choices=[Choice(index=0, finish_reason="stop", delta=ChoiceDelta(content="subagent result"))]
                        )])
                    # Parent first call: invoke Task
                    if not any(m.get("role") == "tool" for m in messages):
                        return FakeStream([ChatCompletionChunk(
                            id="p1", created=0, model=model, object="chat.completion.chunk",
                            choices=[Choice(index=0, finish_reason="tool_calls", delta=ChoiceDelta(
                                tool_calls=[{
                                    "index": 0, "id": "c1", "type": "function",
                                    "function": {"name": "Task", "arguments": json.dumps({"description": "test", "prompt": "just say hi"})}
                                }]
                            ))]
                        )])
                    # Parent after Task result: final message
                    return FakeStream([ChatCompletionChunk(
                        id="p2", created=0, model=model, object="chat.completion.chunk",
                        choices=[Choice(index=0, finish_reason="stop", delta=ChoiceDelta(content="parent done"))]
                    )])

    import app.agent as agent_mod
    orig = agent_mod._client
    agent_mod._client = lambda s: FakeClient()

    # Collect subagent events via a test responder
    class TestResponder(UserResponder):
        def __init__(self):
            super().__init__()
            self.events = []
        async def send_event(self, evt):
            self.events.append(evt)
    responder = TestResponder()

    try:
        s = Session(api_key="fake", model="fake-model")
        events = []
        async for evt in run_agent_loop(s, "delegate to a subagent", responder=responder):
            events.append(evt)
        types = [e["type"] for e in events]
        # Should see parent's tool.call for Task, then subagent.* events via responder, then tool.result
        assert any(e["type"] == "tool.call" and e["name"] == "Task" for e in events), types
        # Subagent events are emitted via responder, not yielded by the parent loop
        sub_events = responder.events
        sub_types = [e["type"] for e in sub_events]
        assert "subagent.start" in sub_types, sub_types
        assert "subagent.assistant.message" in sub_types, sub_types
        assert "subagent.end" in sub_types, sub_types
        # The Task tool result should contain the subagent's final text
        task_result = next(e for e in events if e["type"] == "tool.result" and e["name"] == "Task")
        assert "subagent result" in task_result["output"], task_result["output"]
        print("[ok] Task tool spawns subagent, returns its final answer")
        print("     subagent events:", sub_types)
    finally:
        agent_mod._client = orig


async def main():
    test_workspace_layout()
    test_path_sandbox()
    test_openai_tools_schema()
    await test_core_tools()
    await test_skill_tool()
    await test_outline_and_complete_tools()
    await test_ask_user_question_tool()
    await test_agent_loop_mocked()
    await test_subagent_tool_mocked()
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
