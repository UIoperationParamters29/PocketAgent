"""The agent loop — the heart of PocketAgent.

Mirrors z.ai agentic mode:
  user message → LLM streams thinking → optional tool_calls → tool_results
              → LLM streams next → ... → final assistant message

All events are streamed over the WebSocket as they happen, so the phone UI
can render the z.ai-style "thinking / tool-call / result" cards live.

Bidirectional tools (AskUserQuestion) use UserResponder to coordinate with
the WS handler: the agent emits a `user.question` event and awaits a future;
the WS handler resolves the future when the phone sends a `user.answer` frame.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from openai import AsyncOpenAI

from .config import settings
from .llm import stream_chat, StreamEvent
from .tools import ToolContext, call_tool, tools_for_depth


# --------------------------------------------------------------------------- #
# UserResponder — bridges agent loop ↔ WS handler for bidirectional flow
# --------------------------------------------------------------------------- #
class UserResponder:
    """The agent loop calls .ask() to block on a user answer; the WS handler
    calls .resolve() when the phone sends `user.answer`.

    Also exposes .send_event() for tools that just need to push an event
    (Outline, Complete) without blocking.
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future] = {}
        # Sentinels for clean shutdown
        self._closed = False

    async def send_event(self, evt: dict[str, Any]) -> None:
        """Subclasses (or the WS handler) override this to actually send."""
        # Default: no-op (used in tests where we don't care about events)
        pass

    async def ask(self, question_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Emit a user.question event and await the user's answer."""
        if self._closed:
            return None
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[question_id] = fut
        try:
            await self.send_event({"type": "user.question", "question_id": question_id, **payload})
        except Exception:
            self._pending.pop(question_id, None)
            return None
        try:
            return await asyncio.wait_for(fut, timeout=300.0)  # 5 min cap
        except asyncio.TimeoutError:
            self._pending.pop(question_id, None)
            return None

    def resolve(self, question_id: str, answer: dict[str, Any]) -> bool:
        """WS handler calls this when phone sends user.answer."""
        fut = self._pending.pop(question_id, None)
        if fut is None or fut.done():
            return False
        fut.set_result(answer)
        return True

    def close(self) -> None:
        """Cancel any pending futures (WS closed)."""
        self._closed = True
        for qid, fut in list(self._pending.items()):
            if not fut.done():
                fut.cancel()
        self._pending.clear()


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #
@dataclass
class Session:
    """A single agent session — one phone chat thread."""
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    messages: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    started_at: float = field(default_factory=time.time)

    # Per-session LLM config (BYOK — sent by the phone on connect, never stored)
    base_url: str = settings.default_base_url
    api_key: str = settings.default_api_key
    model: str = settings.default_model

    # Subagent tuning
    max_iterations: int = settings.max_iterations


# --------------------------------------------------------------------------- #
# System prompts
# --------------------------------------------------------------------------- #
def _system_prompt() -> str:
    """The agent's identity — mirrors z.ai agentic mode's system prompt."""
    return f"""You are PocketAgent — a personal AI agent running inside your own Linux computer.

# What you are
- You live inside a GitHub Codespace, which is YOUR workspace.
- Your workspace root is: {settings.workspace_root}
- Layout (mirrors z.ai agentic mode):
  - download/   ← final user-facing deliverables (documents, charts, scripts you ship)
  - scripts/    ← persisted generation scripts (Python/Node/Shell)
  - upload/     ← files the user uploaded from their phone
  - skills/     ← modular SKILL.md packages (lazy-loaded on demand)
  - AGENTS.md   ← (optional) custom instructions, read on session start

# How you work
- You have tools: Bash, Read, Write, Edit, Glob, Grep, LS, TodoWrite,
  Skill, Task, AskUserQuestion, Outline, Complete.
- ALWAYS make a todo list before multi-step work (use TodoWrite).
- Persist any non-trivial script to scripts/ before running it (z.ai rule).
- Save final deliverables to download/.
- Never write outside the workspace root.
- Be autonomous — if you lack a tool, install it (apt/pip/npm) inside your workspace.
- Stream your thinking to the user as you work; they're watching on their phone.

# When to use the bidirectional tools
- AskUserQuestion: BEFORE starting a deliverable, batch-ask audience/tone/length/style.
  Skip only if the user already pinned all dimensions or said "just do it".
- Outline: after AskUserQuestion, commit to a section plan before producing.
- Complete: exactly once at the very end, with a brief summary.
- Task: for self-contained subtasks (research, parallel work). Subagents don't
  see this conversation — give them a self-contained prompt.
- Skill: when the user asks for something you have a SKILL.md for (pdf, charts,
  image-generation, etc.). Lazy-load it on demand.

# Tone
- Direct, no fluff. Show what you're doing, not meta-commentary about doing it.
- Match the user's language.

# When to stop
- When the user's request is fully done, call Complete, then give a brief summary (≤100 words).
- If blocked, say so clearly and use AskUserQuestion with exactly one question.
"""


def _subagent_system_prompt(subagent_type: str, depth: int) -> str:
    """The subagent's identity — a focused worker, not the main agent."""
    return f"""You are a PocketAgent subagent (type={subagent_type}, depth={depth}).

You are spawned by the parent agent to handle a self-contained subtask.
You have your own context — the parent does NOT see your work, only your
final answer. Be efficient: do the task, return the result.

You have access to all tools EXCEPT Task, AskUserQuestion, Outline, Complete
(those are parent-only). Use Bash/Read/Write/Edit/Glob/Grep/LS/Skill/TodoWrite.

Workspace root: {settings.workspace_root}
Be concise. When done, give your final answer as your last message.
"""


def _load_agents_md() -> str:
    """Read AGENTS.md from the workspace if present."""
    p = settings.workspace_root / "AGENTS.md"
    if p.exists():
        try:
            return "\n\n# AGENTS.md (user custom instructions)\n" + p.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


def _client(session: Session) -> AsyncOpenAI:
    """DEPRECATED — kept for test backwards-compat. Use stream_chat() directly."""
    if not session.api_key:
        raise ValueError("No API key for this session — the phone must send one on connect.")
    return AsyncOpenAI(base_url=session.base_url, api_key=session.api_key)


def _stream_for_session(session: Session, messages: list[dict], tools: list[dict]):
    """Return an async iterator of StreamEvent from the right provider."""
    return stream_chat(
        base_url=session.base_url,
        api_key=session.api_key,
        model=session.model,
        messages=messages,
        tools=tools,
    )


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #
async def run_agent_loop(
    session: Session,
    user_message: str,
    *,
    responder: Optional[UserResponder] = None,
    depth: int = 0,
    parent_id: Optional[str] = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run one full agent turn: user message → LLM → tools → ... → final.

    Yields events as they happen. The caller (WS handler or subagent spawner)
    forwards them to the phone (with optional prefixing).
    """
    yield _evt("user.message", content=user_message)
    session.messages.append({"role": "user", "content": user_message})

    # First-time system prompt
    if not any(m.get("role") == "system" for m in session.messages):
        if depth == 0:
            sys_prompt = _system_prompt() + _load_agents_md()
        else:
            sys_prompt = _subagent_system_prompt("general-purpose", depth)
        session.messages.insert(0, {"role": "system", "content": sys_prompt})

    client = _stream_for_session  # function reference; called below
    tools = tools_for_depth(depth)

    while session.iterations < session.max_iterations:
        session.iterations += 1

        # ----- Stream the LLM (provider-agnostic) -----
        assistant_text = ""
        tool_calls: list[dict[str, Any]] = []
        try:
            async for evt in client(session, session.messages, tools):
                if evt.kind == "delta":
                    assistant_text += evt.text
                    yield _evt("assistant.delta", content=evt.text)
                elif evt.kind == "tool_call_start":
                    idx = evt.tool_index
                    while len(tool_calls) <= idx:
                        tool_calls.append({"id": "", "name": "", "args": ""})
                    if evt.tool_id:
                        tool_calls[idx]["id"] = evt.tool_id
                    if evt.tool_name:
                        tool_calls[idx]["name"] = evt.tool_name
                elif evt.kind == "tool_call_delta":
                    idx = evt.tool_index
                    while len(tool_calls) <= idx:
                        tool_calls.append({"id": "", "name": "", "args": ""})
                    tool_calls[idx]["args"] += evt.tool_args_delta
                # 'done' is implicit — we just stop iterating
        except Exception as e:
            yield _evt("error", message=f"LLM error: {type(e).__name__}: {e}", kind="llm")
            return

        # ----- Assemble the assistant message -----
        if tool_calls:
            msg: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["args"]},
                    }
                    for tc in tool_calls
                ],
            }
        else:
            msg = {"role": "assistant", "content": assistant_text}
        session.messages.append(msg)

        if assistant_text:
            yield _evt("assistant.message", content=assistant_text)

        # ----- No tool calls → done -----
        if not tool_calls:
            yield _evt(
                "session.end",
                reason="complete",
                total_ms=int((time.time() - session.started_at) * 1000),
                iterations=session.iterations,
            )
            return

        # ----- Execute tools -----
        ctx = ToolContext(session=session, responder=responder, depth=depth)
        for tc in tool_calls:
            call_id = tc["id"] or f"call_{uuid.uuid4().hex[:8]}"
            name = tc["name"]
            try:
                args = json.loads(tc["args"]) if tc["args"] else {}
            except json.JSONDecodeError as e:
                result = __import__("app.tools.registry", fromlist=["ToolResult"]).ToolResult(
                    ok=False, error=f"bad JSON args: {e}", output=""
                )
                args = {}
            yield _evt("tool.call", call_id=call_id, name=name, args=args)

            t0 = time.time()
            result = await call_tool(name, args, ctx)
            duration_ms = int((time.time() - t0) * 1000)
            yield _evt(
                "tool.result",
                call_id=call_id,
                name=name,
                ok=result.ok,
                output=result.output,
                error=result.error,
                duration_ms=duration_ms,
            )
            if name == "TodoWrite" and args.get("todos"):
                yield _evt("todo.update", todos=args["todos"])

            session.messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": result.render_for_llm(),
            })

    yield _evt("warning", message=f"reached max_iterations={session.max_iterations}; stopping")
    yield _evt(
        "session.end",
        reason="max_iterations",
        total_ms=int((time.time() - session.started_at) * 1000),
        iterations=session.iterations,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _evt(type_: str, **kw: Any) -> dict[str, Any]:
    return {"type": type_, "ts": time.time(), **kw}
