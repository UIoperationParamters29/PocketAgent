"""Tool registry — the z.ai agentic-mode tool surface, re-implemented.

Each tool is an async callable: `async def run(args, ctx) -> ToolResult`.

`ToolContext` gives tools access to:
  - session:    the parent Session (BYOK config, message history)
  - responder:  the UserResponder (for AskUserQuestion, Outline, Complete)
  - depth:      subagent nesting depth (0 = top-level; capped at 2)

Tools are sandboxed to the workspace root. Absolute paths are resolved
relative to workspace_root and rejected if they escape it.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel, Field

from ..config import settings


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #
def _resolve_safe(path: str, must_exist: bool = False) -> Path:
    """Resolve `path` against the workspace root, refusing escapes."""
    p = Path(path)
    if not p.is_absolute():
        p = settings.workspace_root / p
    p = p.resolve()
    try:
        p.relative_to(settings.workspace_root.resolve())
    except ValueError as exc:
        raise PermissionError(
            f"Path '{path}' escapes workspace root ({settings.workspace_root})."
        ) from exc
    if must_exist and not p.exists():
        raise FileNotFoundError(f"Not found: {p}")
    return p


# --------------------------------------------------------------------------- #
# Tool schema + context
# --------------------------------------------------------------------------- #
class ToolResult(BaseModel):
    """What every tool returns to the orchestrator."""
    ok: bool = True
    output: str = ""
    error: str = ""

    def render_for_llm(self) -> str:
        if self.ok:
            return self.output
        return f"[ERROR] {self.error}\n{self.output}".rstrip()


@dataclass
class ToolContext:
    """Per-call context handed to every tool."""
    session: Any  # Session — avoid circular import
    responder: Optional[Any] = None  # UserResponder
    depth: int = 0  # 0 = top-level agent; subagents are 1, 2 (cap)


ToolFn = Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult]]


class ToolSpec(BaseModel):
    name: str
    description: str
    json_schema: dict[str, Any]
    run: ToolFn
    # Tools marked subagent_safe=True are available to subagents (depth>0).
    # Task itself is NOT subagent_safe (prevents infinite recursion).
    subagent_safe: bool = True

    model_config = {"arbitrary_types_allowed": True}


# --------------------------------------------------------------------------- #
# Tools — z.ai surface (sync ones wrapped async)
# --------------------------------------------------------------------------- #
async def _tool_bash(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Bash — run a shell command in the workspace."""
    def _run() -> ToolResult:
        cmd = args["command"]
        timeout = int(args.get("timeout", settings.bash_timeout_s))
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=settings.workspace_root,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PATH": os.environ.get("PATH", "")},
            )
            out = (proc.stdout or "") + (proc.stderr and ("\n[stderr]\n" + proc.stderr) or "")
            if len(out) > settings.max_tool_output_chars:
                out = out[: settings.max_tool_output_chars] + f"\n...[truncated, {len(out)} total chars]"
            return ToolResult(
                ok=proc.returncode == 0,
                output=out,
                error="" if proc.returncode == 0 else f"exit {proc.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error=f"timeout after {timeout}s", output="")
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}", output="")
    return await asyncio.to_thread(_run)


async def _tool_read(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Read — read a text file from the workspace."""
    def _run() -> ToolResult:
        try:
            p = _resolve_safe(args["file_path"], must_exist=True)
            if not p.is_file():
                return ToolResult(ok=False, error=f"not a file: {p}", output="")
            limit = args.get("limit")
            offset = args.get("offset", 0)
            text = p.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            if offset:
                lines = lines[offset:]
            if limit:
                lines = lines[:limit]
            rendered = "\n".join(f"{offset + i + 1:>6}\t{ln}" for i, ln in enumerate(lines))
            return ToolResult(output=rendered or "(empty file)")
        except (PermissionError, FileNotFoundError) as e:
            return ToolResult(ok=False, error=str(e), output="")
    return await asyncio.to_thread(_run)


async def _tool_write(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Write — create or overwrite a file in the workspace."""
    def _run() -> ToolResult:
        try:
            p = _resolve_safe(args["file_path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], encoding="utf-8")
            return ToolResult(output=f"wrote {len(args['content'])} bytes to {p}")
        except (PermissionError, OSError) as e:
            return ToolResult(ok=False, error=str(e), output="")
    return await asyncio.to_thread(_run)


async def _tool_edit(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Edit — exact string replacement in a file (z.ai Edit semantics)."""
    def _run() -> ToolResult:
        try:
            p = _resolve_safe(args["file_path"], must_exist=True)
            text = p.read_text(encoding="utf-8", errors="replace")
            old = args["old_str"]
            new = args["new_str"]
            if old not in text:
                return ToolResult(ok=False, error="old_str not found in file", output="")
            replace_all = args.get("replace_all", False)
            if replace_all:
                new_text = text.replace(old, new)
                count = text.count(old)
            else:
                count = text.count(old)
                if count > 1:
                    return ToolResult(
                        ok=False,
                        error=f"old_str matches {count} times; pass replace_all=true or include more context",
                        output="",
                    )
                new_text = text.replace(old, new, 1)
            p.write_text(new_text, encoding="utf-8")
            return ToolResult(output=f"edited {p} ({count} replacement(s))")
        except (PermissionError, FileNotFoundError, OSError) as e:
            return ToolResult(ok=False, error=str(e), output="")
    return await asyncio.to_thread(_run)


async def _tool_glob(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Glob — find files by name pattern."""
    def _run() -> ToolResult:
        import fnmatch
        pattern = args["pattern"]
        path = args.get("path", str(settings.workspace_root))
        try:
            root = _resolve_safe(path)
        except PermissionError as e:
            return ToolResult(ok=False, error=str(e), output="")
        matches: list[Path] = []
        for p in root.rglob("*"):
            try:
                p.relative_to(settings.workspace_root.resolve())
            except ValueError:
                continue
            if fnmatch.fnmatch(p.name, pattern) or fnmatch.fnmatch(str(p), f"*{pattern}*"):
                matches.append(p)
        matches.sort(key=lambda x: str(x.relative_to(settings.workspace_root)))
        if len(matches) > 500:
            matches = matches[:500]
        out = "\n".join(str(m.relative_to(settings.workspace_root)) for m in matches) or "(no matches)"
        if len(matches) == 500:
            out += "\n...[truncated at 500]"
        return ToolResult(output=out)
    return await asyncio.to_thread(_run)


async def _tool_grep(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Grep — ripgrep-powered content search."""
    def _run() -> ToolResult:
        try:
            from ripgrepy import Ripgrepy
        except ImportError:
            return ToolResult(ok=False, error="ripgrep not installed", output="")
        pattern = args["pattern"]
        path = args.get("path", str(settings.workspace_root))
        case_insensitive = bool(args.get("ignore_case", False))
        try:
            root = _resolve_safe(path)
        except PermissionError as e:
            return ToolResult(ok=False, error=str(e), output="")
        try:
            rg = Ripgrepy(pattern, str(root)).with_filename().line_number()
            if case_insensitive:
                rg = rg.ignore_case()
            out = rg.run().as_string
            if len(out) > settings.max_tool_output_chars:
                out = out[: settings.max_tool_output_chars] + "\n...[truncated]"
            return ToolResult(output=out or "(no matches)")
        except Exception as e:
            msg = str(e)
            if "exit status 1" in msg:
                return ToolResult(output="(no matches)")
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}", output="")
    return await asyncio.to_thread(_run)


async def _tool_ls(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """LS — list a directory's contents."""
    def _run() -> ToolResult:
        try:
            p = _resolve_safe(args["path"], must_exist=True)
            if not p.is_dir():
                return ToolResult(ok=False, error=f"not a directory: {p}", output="")
            ignore = set(args.get("ignore", []) or [])
            entries = []
            for entry in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
                if entry.name in ignore:
                    continue
                kind = "dir " if entry.is_dir() else "file"
                size = entry.stat().st_size if entry.is_file() else ""
                entries.append(f"{kind}  {entry.name:<40} {size}")
            return ToolResult(output="\n".join(entries) or "(empty)")
        except (PermissionError, FileNotFoundError) as e:
            return ToolResult(ok=False, error=str(e), output="")
    return await asyncio.to_thread(_run)


async def _tool_todowrite(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """TodoWrite — the agent's persistent todo list."""
    def _run() -> ToolResult:
        todos = args.get("todos", [])
        store = settings.workspace_root / ".pocketagent" / "todos.json"
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps(todos, indent=2), encoding="utf-8")
        lines = []
        for i, t in enumerate(todos, 1):
            mark = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}.get(t.get("status"), "[ ]")
            lines.append(f"{i}. {mark} {t.get('content','')}")
        return ToolResult(output="todos saved:\n" + "\n".join(lines))
    return await asyncio.to_thread(_run)


# --------------------------------------------------------------------------- #
# Tools — the new z.ai-parity tools (Phase 3)
# --------------------------------------------------------------------------- #
async def _tool_skill(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Skill — lazily load a SKILL.md package from the workspace.

    Mirrors z.ai: the agent discovers a skill by name and reads its
    SKILL.md to learn how to do something it couldn't before.
    """
    name = args["name"]
    skill_dir = settings.workspace_root / "skills" / name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        # Available skills list — helps the agent self-correct
        available = []
        skills_root = settings.workspace_root / "skills"
        if skills_root.exists():
            available = sorted([d.name for d in skills_root.iterdir() if d.is_dir() and (d / "SKILL.md").exists()])
        return ToolResult(
            ok=False,
            error=f"skill '{name}' not found at {skill_md}",
            output=f"Available skills: {available}" if available else "(no skills installed)",
        )
    content = skill_md.read_text(encoding="utf-8", errors="replace")
    # List subdirs so the agent knows what's available to drill into
    subdirs = sorted([d.name for d in skill_dir.iterdir() if d.is_dir()])
    files = sorted([f.name for f in skill_dir.iterdir() if f.is_file() and f.name != "SKILL.md"])
    header = f"# Skill: {name}\nSubdirs: {subdirs}\nOther files: {files}\n\n---\n\n"
    return ToolResult(output=header + content)


async def _tool_task(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Task — spawn a subagent with its own context.

    Mirrors z.ai: the parent agent delegates a self-contained subtask to a
    fresh subagent. The subagent has its own message history, runs the same
    tool-calling loop, and returns its final answer to the parent.
    """
    # Lazy import to avoid circular dependency
    from ..agent import run_agent_loop, Session, _subagent_system_prompt

    description = args.get("description", "")
    prompt = args["prompt"]
    subagent_type = args.get("subagent_type", "general-purpose")
    model = args.get("model", ctx.session.model)  # subagent can use a different model

    if ctx.depth >= 2:
        return ToolResult(
            ok=False,
            error=f"max subagent depth (2) reached (current depth={ctx.depth})",
            output="",
        )

    # Build the sub-session
    sub = Session(
        api_key=ctx.session.api_key,
        base_url=ctx.session.base_url,
        model=model,
    )
    sub.messages = [{"role": "system", "content": _subagent_system_prompt(subagent_type, ctx.depth + 1)}]

    sub_id = sub.session_id
    if ctx.responder:
        await ctx.responder.send_event({
            "type": "subagent.start",
            "subagent_id": sub_id,
            "subagent_type": subagent_type,
            "description": description,
            "depth": ctx.depth + 1,
        })

    final_text = ""
    try:
        async for evt in run_agent_loop(
            sub,
            prompt,
            responder=ctx.responder,
            depth=ctx.depth + 1,
            parent_id=ctx.session.session_id,
        ):
            # Re-emit with subagent. prefix for the phone UI
            if ctx.responder:
                prefixed = {**evt, "type": f"subagent.{evt['type']}", "subagent_id": sub_id}
                await ctx.responder.send_event(prefixed)
            if evt["type"] == "assistant.message":
                final_text = evt.get("content", "")
            if evt["type"] == "error":
                # Subagent errored — break and surface to parent
                final_text = f"[subagent error: {evt.get('message','')}]"
                break
    finally:
        if ctx.responder:
            await ctx.responder.send_event({
                "type": "subagent.end",
                "subagent_id": sub_id,
                "depth": ctx.depth + 1,
            })

    return ToolResult(output=final_text or "(subagent produced no output)")


async def _tool_ask_user_question(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """AskUserQuestion — pause and ask the user a structured question.

    Mirrors z.ai: the agent emits a question with multiple choice options;
    the phone renders a card; the user picks; the agent resumes.
    """
    if not ctx.responder:
        return ToolResult(ok=False, error="no responder available (subagent context)", output="")
    questions = args.get("questions", [])
    if not questions:
        return ToolResult(ok=False, error="no questions provided", output="")
    question_id = uuid.uuid4().hex[:12]
    answer = await ctx.responder.ask(question_id, {"questions": questions})
    if answer is None:
        return ToolResult(ok=False, error="user did not answer (timeout/disconnect)", output="")
    # Return the answers as JSON for the LLM
    return ToolResult(output=json.dumps(answer, ensure_ascii=False, indent=2))


async def _tool_outline(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Outline — submit a structured outline to the phone UI.

    Mirrors z.ai: the agent commits to a plan (sections) before producing
    the deliverable. The phone shows it as a roadmap card.
    """
    if not ctx.responder:
        return ToolResult(ok=False, error="no responder available", output="")
    document_type = args.get("document_type", "word")
    sections = args.get("sections", [])
    design = args.get("design")
    await ctx.responder.send_event({
        "type": "outline.update",
        "document_type": document_type,
        "sections": sections,
        "design": design,
    })
    summary = f"outline submitted ({len(sections)} sections, type={document_type})"
    return ToolResult(output=summary)


async def _tool_complete(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Complete — signal that the deliverable is done.

    Mirrors z.ai: the agent explicitly marks the project complete with a
    project_type and summary. The phone shows a completion card with
    download links if any files were produced.
    """
    if not ctx.responder:
        return ToolResult(ok=False, error="no responder available", output="")
    project_type = args.get("project_type", "")
    summary = args.get("summary", "")
    await ctx.responder.send_event({
        "type": "session.complete",
        "project_type": project_type,
        "summary": summary,
    })
    return ToolResult(output=f"project marked complete (type={project_type})")


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
TOOLS: dict[str, ToolSpec] = {
    "Bash": ToolSpec(
        name="Bash",
        description=(
            "Execute a bash command in the agent's workspace. The workspace is "
            "the agent's own Linux computer — full sudo is NOT available by "
            "default, but apt/pip/npm work if pre-installed. Use this for running "
            "scripts, listing files, git, installing packages, etc. Output is "
            "truncated at 30,000 chars."
        ),
        json_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to run."},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 120).", "default": 120},
            },
            "required": ["command"],
        },
        run=_tool_bash,
    ),
    "Read": ToolSpec(
        name="Read",
        description="Read a text file from the workspace. Returns cat -n style output.",
        json_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "offset": {"type": "integer", "default": 0},
                "limit": {"type": "integer", "default": 2000},
            },
            "required": ["file_path"],
        },
        run=_tool_read,
    ),
    "Write": ToolSpec(
        name="Write",
        description="Create or overwrite a file in the workspace. Directories are created as needed.",
        json_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
        },
        run=_tool_write,
    ),
    "Edit": ToolSpec(
        name="Edit",
        description="Exact string replacement in an existing file. old_str must be unique unless replace_all=true.",
        json_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["file_path", "old_str", "new_str"],
        },
        run=_tool_edit,
    ),
    "Glob": ToolSpec(
        name="Glob",
        description="Find files by name pattern (e.g., '**/*.py'). Searches the workspace.",
        json_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "default": "."},
            },
            "required": ["pattern"],
        },
        run=_tool_glob,
    ),
    "Grep": ToolSpec(
        name="Grep",
        description="Search file contents using ripgrep. Returns matching lines with file:line prefixes.",
        json_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex or literal pattern to search for."},
                "path": {"type": "string", "default": "."},
                "ignore_case": {"type": "boolean", "default": False},
            },
            "required": ["pattern"],
        },
        run=_tool_grep,
    ),
    "LS": ToolSpec(
        name="LS",
        description="List the contents of a directory in the workspace.",
        json_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "ignore": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["path"],
        },
        run=_tool_ls,
    ),
    "TodoWrite": ToolSpec(
        name="TodoWrite",
        description="Update the agent's todo list. Each todo has id, content, status (pending|in_progress|completed), priority (high|medium|low).",
        json_schema={
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                        },
                        "required": ["id", "content", "status", "priority"],
                    },
                }
            },
            "required": ["todos"],
        },
        run=_tool_todowrite,
    ),
    "Skill": ToolSpec(
        name="Skill",
        description=(
            "Load a SKILL.md package from the workspace's skills/ directory. "
            "Skills teach you how to do things you couldn't before (e.g., 'pdf', "
            "'charts', 'image-generation'). Pass the skill name; returns the "
            "SKILL.md content plus the list of subdirs (briefs, configs, scripts, "
            "references) you can drill into with Read."
        ),
        json_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name, e.g. 'pdf' or 'charts'."},
            },
            "required": ["name"],
        },
        run=_tool_skill,
    ),
    "Task": ToolSpec(
        name="Task",
        description=(
            "Spawn a subagent with its own context to handle a self-contained "
            "subtask. The subagent runs the same tool-calling loop and returns "
            "its final answer to you. Use for: research, parallel work, complex "
            "sub-steps you don't want cluttering your context. Max nesting depth: 2."
        ),
        json_schema={
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Short 3-5 word label for the subtask."},
                "prompt": {"type": "string", "description": "Self-contained instructions for the subagent. It will NOT see this conversation."},
                "subagent_type": {"type": "string", "default": "general-purpose"},
                "model": {"type": "string", "description": "Optional: override the model for this subagent."},
            },
            "required": ["description", "prompt"],
        },
        run=_tool_task,
        subagent_safe=False,  # prevents infinite recursion
    ),
    "AskUserQuestion": ToolSpec(
        name="AskUserQuestion",
        description=(
            "Pause and ask the user a structured question with multiple choice "
            "options. Use BEFORE starting work on a deliverable to confirm "
            "audience / tone / length / style / etc. The user sees a card on "
            "their phone and picks an option (or types a custom answer)."
        ),
        json_schema={
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "1-8 questions to ask in one batch.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "header": {"type": "string", "description": "Short chip-style label, ≤12 chars."},
                            "type": {"type": "string", "enum": ["single", "multi"]},
                            "options": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "description": {"type": "string"},
                                        "recommended": {"type": "boolean"},
                                    },
                                    "required": ["label", "description"],
                                },
                            },
                        },
                        "required": ["question", "header", "type", "options"],
                    },
                }
            },
            "required": ["questions"],
        },
        run=_tool_ask_user_question,
        subagent_safe=False,  # subagents can't block on user input
    ),
    "Outline": ToolSpec(
        name="Outline",
        description=(
            "Submit a structured outline (sections) to the phone UI before "
            "producing a deliverable. The user sees a roadmap card. Call this "
            "once per deliverable, after any AskUserQuestion clarification."
        ),
        json_schema={
            "type": "object",
            "properties": {
                "document_type": {"type": "string", "enum": ["ppt", "word", "excel", "pdf"]},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "title": {"type": "string"},
                            "task_brief": {"type": "string"},
                            "layout": {"type": "string"},
                        },
                        "required": ["index", "title", "task_brief"],
                    },
                },
                "design": {
                    "type": "object",
                    "properties": {
                        "style_name": {"type": "string"},
                        "palette": {"type": "object"},
                        "typography": {"type": "string"},
                        "reference": {"type": "string"},
                    },
                },
            },
            "required": ["document_type", "sections"],
        },
        run=_tool_outline,
        subagent_safe=False,
    ),
    "Complete": ToolSpec(
        name="Complete",
        description=(
            "Signal that the deliverable is done. Call this exactly once at the "
            "end of a project, with a brief summary. The phone shows a "
            "completion card; if any files were saved to download/, they appear "
            "as download links."
        ),
        json_schema={
            "type": "object",
            "properties": {
                "project_type": {"type": "string", "description": "e.g., 'web_dev', 'document', 'chart'"},
                "summary": {"type": "string", "description": "Brief summary of what was produced."},
            },
            "required": ["project_type", "summary"],
        },
        run=_tool_complete,
        subagent_safe=False,
    ),
}


def to_openai_tools(include: Optional[set[str]] = None) -> list[dict[str, Any]]:
    """Return the OpenAI-format `tools` array. Optionally filter by name set."""
    out = []
    for spec in TOOLS.values():
        if include is not None and spec.name not in include:
            continue
        out.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.json_schema,
            },
        })
    return out


def tools_for_depth(depth: int) -> list[dict[str, Any]]:
    """Return the tools available at a given subagent depth."""
    if depth == 0:
        return to_openai_tools()
    # Subagents: everything except non-subagent_safe tools
    safe = {name for name, spec in TOOLS.items() if spec.subagent_safe}
    return to_openai_tools(safe)


async def call_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Run a tool by name."""
    spec = TOOLS.get(name)
    if spec is None:
        return ToolResult(ok=False, error=f"unknown tool: {name}", output="")
    try:
        return await spec.run(args, ctx)
    except Exception as e:
        return ToolResult(ok=False, error=f"{type(e).__name__}: {e}", output="")
