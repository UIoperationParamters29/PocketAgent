"""The agent loop — the heart of PocketAgent.

Mirrors z.ai agentic mode:
  user message → LLM streams thinking → optional tool_calls → tool_results
              → LLM streams next → ... → final assistant message

All events are streamed over the WebSocket as they happen, so the phone UI
can render the z.ai-style "thinking / tool-call / result" cards live.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

import anyio
from openai import AsyncOpenAI

from .config import settings
from .tools import TOOLS, ToolResult, call_tool, to_openai_tools


# --------------------------------------------------------------------------- #
# Event protocol (phone <-> cloud)
# --------------------------------------------------------------------------- #
# Every event is a JSON object with at least {type, ts}. The phone UI renders
# each type as a card. This is the contract — keep it stable.
EVENT_TYPES = {
    "session.start",      # {session_id, workspace, model, tools}
    "user.message",       # {content}
    "assistant.delta",    # {content}            ← streamed token-by-token
    "assistant.message",  # {content}            ← final assembled message
    "tool.call",          # {call_id, name, args}
    "tool.result",        # {call_id, name, ok, output, error, duration_ms}
    "todo.update",        # {todos}
    "error",              # {message, kind}
    "session.end",        # {reason, total_ms, iterations}
    "warning",            # {message}
}


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
- You have tools: Bash, Read, Write, Edit, Glob, Grep, LS, TodoWrite.
- Always make a todo list before multi-step work (use TodoWrite).
- Persist any non-trivial script to scripts/ before running it (z.ai rule).
- Save final deliverables to download/.
- Never write outside the workspace root.
- Be autonomous — if you lack a tool, install it (apt/pip/npm) inside your workspace.
- Stream your thinking to the user as you work; they're watching on their phone.

# Tone
- Direct, no fluff. Show what you're doing, not meta-commentary about doing it.
- Match the user's language.

# When to stop
- When the user's request is fully done, give a brief summary (≤100 words).
- If blocked, say so clearly and ask exactly one clarifying question.
"""


def _load_agents_md() -> str:
    """Read AGENTS.md from the workspace if present (z.ai pattern)."""
    p = settings.workspace_root / "AGENTS.md"
    if p.exists():
        try:
            return "\n\n# AGENTS.md (user custom instructions)\n" + p.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


def _client(session: Session) -> AsyncOpenAI:
    """Build an OpenAI client for this session's BYOK config."""
    if not session.api_key:
        raise ValueError("No API key for this session — the phone must send one on connect.")
    return AsyncOpenAI(base_url=session.base_url, api_key=session.api_key)


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #
async def run_agent_loop(
    session: Session,
    user_message: str,
) -> AsyncIterator[dict[str, Any]]:
    """Run one full agent turn: user message → LLM → tools → ... → final.

    Yields events as they happen (see EVENT_TYPES). The caller (WebSocket
    handler) forwards them to the phone.
    """
    yield _evt("user.message", content=user_message)
    session.messages.append({"role": "user", "content": user_message})

    # First-time system prompt
    if not any(m.get("role") == "system" for m in session.messages):
        session.messages.insert(0, {"role": "system", "content": _system_prompt() + _load_agents_md()})

    client = _client(session)
    tools = to_openai_tools()

    while session.iterations < settings.max_iterations:
        session.iterations += 1

        # ----- Stream the LLM -----
        assistant_text = ""
        tool_calls: list[dict[str, Any]] = []
        try:
            stream = await client.chat.completions.create(
                model=session.model,
                messages=session.messages,
                tools=tools,
                tool_choice="auto",
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                if delta.content:
                    assistant_text += delta.content
                    yield _evt("assistant.delta", content=delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        while len(tool_calls) <= idx:
                            tool_calls.append({"id": "", "name": "", "args": ""})
                        if tc.id:
                            tool_calls[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_calls[idx]["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_calls[idx]["args"] += tc.function.arguments
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
            yield _evt("session.end", reason="complete", total_ms=int((time.time() - session.started_at) * 1000), iterations=session.iterations)
            return

        # ----- Execute tools -----
        for tc in tool_calls:
            call_id = tc["id"] or f"call_{uuid.uuid4().hex[:8]}"
            name = tc["name"]
            try:
                args = json.loads(tc["args"]) if tc["args"] else {}
            except json.JSONDecodeError as e:
                result = ToolResult(ok=False, error=f"bad JSON args: {e}", output="")
                args = {}
            yield _evt("tool.call", call_id=call_id, name=name, args=args)

            if name not in TOOLS:
                result = ToolResult(ok=False, error=f"unknown tool: {name}", output="")
            else:
                t0 = time.time()
                result = await call_tool(name, args)
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
                # If the tool was TodoWrite, also emit a todo.update event
                if name == "TodoWrite" and args.get("todos"):
                    yield _evt("todo.update", todos=args["todos"])

            # Append tool_result to messages for next LLM call
            session.messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": result.render_for_llm(),
            })

    # Hit iteration cap
    yield _evt("warning", message=f"reached max_iterations={settings.max_iterations}; stopping")
    yield _evt("session.end", reason="max_iterations", total_ms=int((time.time() - session.started_at) * 1000), iterations=session.iterations)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _evt(type_: str, **kw: Any) -> dict[str, Any]:
    return {"type": type_, "ts": time.time(), **kw}
