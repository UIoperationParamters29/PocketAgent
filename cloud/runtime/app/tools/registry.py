"""Tool registry — the z.ai agentic-mode tool surface, re-implemented.

Each tool is a callable with:
  - name:           the LLM-visible function name
  - description:    plain-English description for the LLM
  - json_schema:    OpenAI/JSON-schema for the tool's args
  - run(**kwargs):  executes against the workspace, returns a string

Tools are sandboxed to the workspace root. Absolute paths are resolved
relative to workspace_root and rejected if they escape it.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

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
# Tool schema
# --------------------------------------------------------------------------- #
class ToolSpec(BaseModel):
    name: str
    description: str
    json_schema: dict[str, Any]  # OpenAI function-tool "parameters" schema
    run: Callable[[dict[str, Any]], "ToolResult"]

    model_config = {"arbitrary_types_allowed": True}


class ToolResult(BaseModel):
    """What every tool returns to the orchestrator."""
    ok: bool = True
    output: str = ""
    error: str = ""

    def render_for_llm(self) -> str:
        """Compact string form for the LLM's tool_result message."""
        if self.ok:
            return self.output
        return f"[ERROR] {self.error}\n{self.output}".rstrip()


# --------------------------------------------------------------------------- #
# Tools — z.ai surface
# --------------------------------------------------------------------------- #
def _tool_bash(args: dict[str, Any]) -> ToolResult:
    """Bash — run a shell command in the workspace (the agent's computer)."""
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
            # Agent sees a clean env; BYOK keys are NEVER inherited.
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
        out = (proc.stdout or "") + (proc.stderr and ("\n[stderr]\n" + proc.stderr) or "")
        if len(out) > settings.max_tool_output_chars:
            out = out[: settings.max_tool_output_chars] + f"\n...[truncated, {len(out)} total chars]"
        return ToolResult(ok=proc.returncode == 0, output=out, error="" if proc.returncode == 0 else f"exit {proc.returncode}")
    except subprocess.TimeoutExpired:
        return ToolResult(ok=False, error=f"timeout after {timeout}s", output="")
    except Exception as e:
        return ToolResult(ok=False, error=f"{type(e).__name__}: {e}", output="")


def _tool_read(args: dict[str, Any]) -> ToolResult:
    """Read — read a text file from the workspace."""
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
        # cat -n style numbering
        rendered = "\n".join(f"{offset + i + 1:>6}\t{ln}" for i, ln in enumerate(lines))
        return ToolResult(output=rendered or "(empty file)")
    except (PermissionError, FileNotFoundError) as e:
        return ToolResult(ok=False, error=str(e), output="")


def _tool_write(args: dict[str, Any]) -> ToolResult:
    """Write — create or overwrite a file in the workspace."""
    try:
        p = _resolve_safe(args["file_path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"], encoding="utf-8")
        return ToolResult(output=f"wrote {len(args['content'])} bytes to {p}")
    except (PermissionError, OSError) as e:
        return ToolResult(ok=False, error=str(e), output="")


def _tool_edit(args: dict[str, Any]) -> ToolResult:
    """Edit — exact string replacement in a file (z.ai Edit semantics)."""
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
        return ToolResult(output=f"edited {p} ({count if not replace_all else 'all'} replacement(s))")
    except (PermissionError, FileNotFoundError, OSError) as e:
        return ToolResult(ok=False, error=str(e), output="")


def _tool_glob(args: dict[str, Any]) -> ToolResult:
    """Glob — find files by name pattern."""
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


def _tool_grep(args: dict[str, Any]) -> ToolResult:
    """Grep — ripgrep-powered content search."""
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
        # ripgrep returns exit code 1 when no matches — that's not an error.
        if "returned non-zero exit status 1" in msg or "exit status 1" in msg:
            return ToolResult(output="(no matches)")
        return ToolResult(ok=False, error=f"{type(e).__name__}: {e}", output="")


def _tool_ls(args: dict[str, Any]) -> ToolResult:
    """LS — list a directory's contents (the z.ai LS tool)."""
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


def _tool_todowrite(args: dict[str, Any]) -> ToolResult:
    """TodoWrite — the agent's persistent todo list (z.ai pattern)."""
    todos = args.get("todos", [])
    store = settings.workspace_root / ".pocketagent" / "todos.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    import json
    store.write_text(json.dumps(todos, indent=2), encoding="utf-8")
    # Render as a checklist for the LLM
    lines = []
    for i, t in enumerate(todos, 1):
        mark = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}.get(t.get("status"), "[ ]")
        lines.append(f"{i}. {mark} {t.get('content','')}")
    return ToolResult(output="todos saved:\n" + "\n".join(lines))


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
                "path": {"type": "string", "default": ".", "description": "Directory or file to search in. Default: workspace root."},
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
}


def to_openai_tools() -> list[dict[str, Any]]:
    """Return the OpenAI-format `tools` array for chat.completions."""
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.json_schema,
            },
        }
        for spec in TOOLS.values()
    ]


async def call_tool(name: str, args: dict[str, Any]) -> ToolResult:
    """Run a tool by name, async-safe (sync tools run in a thread)."""
    spec = TOOLS.get(name)
    if spec is None:
        return ToolResult(ok=False, error=f"unknown tool: {name}", output="")
    # All our tools are sync CPU/IO work — offload to a thread.
    return await asyncio.to_thread(spec.run, args)
