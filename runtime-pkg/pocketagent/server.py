"""PocketAgent runtime server — FastAPI + WebSocket.

This runs inside Termux on the phone. The phone APK connects to ws://127.0.0.1:8080/agent.
The agent calls the user's LLM directly (BYOK key sent from APK), executes tools
in the Termux workspace, and streams events back.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

# Workspace = ~/pocketagent-workspace (persists across restarts in Termux)
WORKSPACE = Path.home() / "pocketagent-workspace"
for sub in ("download", "scripts", "upload", "skills", ".pocketagent"):
    (WORKSPACE / sub).mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Lifespan
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[PocketAgent] Workspace: {WORKSPACE}")
    print(f"[PocketAgent] Ready on http://127.0.0.1:8080")
    yield


app = FastAPI(title="PocketAgent Runtime", version="0.5.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --------------------------------------------------------------------------- #
# HTTP endpoints
# --------------------------------------------------------------------------- #
@app.get("/")
async def root():
    return {"name": "PocketAgent Runtime", "version": "0.5.0", "workspace": str(WORKSPACE)}


@app.get("/workspace")
async def workspace_tree(depth: int = 3):
    """JSON snapshot of the workspace tree."""
    def build(p: Path, d: int) -> dict:
        node = {"name": p.name or str(p), "path": str(p.relative_to(WORKSPACE)) if p != WORKSPACE else "", "type": "dir" if p.is_dir() else "file"}
        if p.is_dir() and d > 0:
            try:
                node["children"] = [build(c, d - 1) for c in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))]
            except PermissionError:
                node["children"] = []
        elif p.is_file():
            try: node["size"] = p.stat().st_size
            except OSError: node["size"] = 0
        return node
    return build(WORKSPACE, depth)


@app.get("/file")
async def read_file(path: str):
    """Read a file's contents."""
    p = _resolve_safe(path)
    if not p or not p.exists() or not p.is_file():
        return {"ok": False, "error": "not found or not a file"}
    data = p.read_bytes()
    if len(data) > 200_000:
        return {"ok": True, "path": str(p), "truncated": True, "size": len(data), "content": data[:200_000].decode("utf-8", errors="replace")}
    return {"ok": True, "path": str(p), "truncated": False, "size": len(data), "content": data.decode("utf-8", errors="replace")}


# --------------------------------------------------------------------------- #
# Tools (the full z.ai-parity surface)
# --------------------------------------------------------------------------- #
def _resolve_safe(path: str, must_exist: bool = False) -> Optional[Path]:
    """Resolve path against WORKSPACE, refusing escapes."""
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE / p
    p = p.resolve()
    try:
        p.relative_to(WORKSPACE.resolve())
    except ValueError:
        return None
    if must_exist and not p.exists():
        return None
    return p


async def _tool_bash(args: dict) -> dict:
    cmd = args["command"]
    timeout = int(args.get("timeout", 120))
    def _run():
        try:
            proc = subprocess.run(cmd, shell=True, cwd=WORKSPACE, capture_output=True, text=True, timeout=timeout)
            out = (proc.stdout or "") + (proc.stderr and "\n[stderr]\n" + proc.stderr or "")
            if len(out) > 30000: out = out[:30000] + f"\n...[truncated, {len(out)} total]"
            return {"ok": proc.returncode == 0, "output": out, "error": "" if proc.returncode == 0 else f"exit {proc.returncode}"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "", "error": f"timeout after {timeout}s"}
        except Exception as e:
            return {"ok": False, "output": "", "error": f"{type(e).__name__}: {e}"}
    return await asyncio.to_thread(_run)


async def _tool_read(args: dict) -> dict:
    def _run():
        p = _resolve_safe(args["file_path"], must_exist=True)
        if not p or not p.is_file(): return {"ok": False, "error": "not found or not a file", "output": ""}
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        off = args.get("offset", 0); lim = args.get("limit", 2000)
        lines = lines[off:off+lim]
        return {"ok": True, "output": "\n".join(f"{off+i+1:>6}\t{ln}" for i, ln in enumerate(lines)) or "(empty)", "error": ""}
    return await asyncio.to_thread(_run)


async def _tool_write(args: dict) -> dict:
    def _run():
        p = _resolve_safe(args["file_path"])
        if not p: return {"ok": False, "error": "path escapes workspace", "output": ""}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"], encoding="utf-8")
        return {"ok": True, "output": f"wrote {len(args['content'])} bytes to {p.relative_to(WORKSPACE)}", "error": ""}
    return await asyncio.to_thread(_run)


async def _tool_edit(args: dict) -> dict:
    def _run():
        p = _resolve_safe(args["file_path"], must_exist=True)
        if not p: return {"ok": False, "error": "not found", "output": ""}
        text = p.read_text(encoding="utf-8", errors="replace")
        old, new = args["old_str"], args["new_str"]
        if old not in text: return {"ok": False, "error": "old_str not found", "output": ""}
        replace_all = args.get("replace_all", False)
        if replace_all:
            count = text.count(old); text = text.replace(old, new)
        else:
            count = text.count(old)
            if count > 1: return {"ok": False, "error": f"old_str matches {count} times; pass replace_all=true", "output": ""}
            text = text.replace(old, new, 1)
        p.write_text(text, encoding="utf-8")
        return {"ok": True, "output": f"edited {p.relative_to(WORKSPACE)} ({count} replacement(s))", "error": ""}
    return await asyncio.to_thread(_run)


async def _tool_glob(args: dict) -> dict:
    def _run():
        import fnmatch
        pattern = args["pattern"]
        root = _resolve_safe(args.get("path", ".")) or WORKSPACE
        matches = []
        for p in root.rglob("*"):
            if fnmatch.fnmatch(p.name, pattern) or fnmatch.fnmatch(str(p), f"*{pattern}*"):
                matches.append(p)
        matches.sort(key=lambda x: str(x.relative_to(WORKSPACE)))
        if len(matches) > 500: matches = matches[:500]
        out = "\n".join(str(m.relative_to(WORKSPACE)) for m in matches) or "(no matches)"
        return {"ok": True, "output": out, "error": ""}
    return await asyncio.to_thread(_run)


async def _tool_grep(args: dict) -> dict:
    def _run():
        try:
            from ripgrepy import Ripgrepy
        except ImportError:
            return {"ok": False, "error": "ripgrep not installed (run: pkg install ripgrep)", "output": ""}
        root = _resolve_safe(args.get("path", ".")) or WORKSPACE
        rg = Ripgrepy(args["pattern"], str(root)).with_filename().line_number()
        if args.get("ignore_case"): rg = rg.ignore_case()
        try:
            out = rg.run().as_string
            if len(out) > 30000: out = out[:30000] + "\n...[truncated]"
            return {"ok": True, "output": out or "(no matches)", "error": ""}
        except Exception as e:
            if "exit status 1" in str(e): return {"ok": True, "output": "(no matches)", "error": ""}
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "output": ""}
    return await asyncio.to_thread(_run)


async def _tool_ls(args: dict) -> dict:
    def _run():
        p = _resolve_safe(args["path"], must_exist=True)
        if not p or not p.is_dir(): return {"ok": False, "error": "not a dir", "output": ""}
        ignore = set(args.get("ignore", []) or [])
        entries = []
        for entry in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            if entry.name in ignore: continue
            kind = "dir " if entry.is_dir() else "file"
            size = entry.stat().st_size if entry.is_file() else ""
            entries.append(f"{kind}  {entry.name:<40} {size}")
        return {"ok": True, "output": "\n".join(entries) or "(empty)", "error": ""}
    return await asyncio.to_thread(_run)


async def _tool_todowrite(args: dict) -> dict:
    def _run():
        (WORKSPACE / ".pocketagent").mkdir(exist_ok=True)
        (WORKSPACE / ".pocketagent" / "todos.json").write_text(json.dumps(args.get("todos", []), indent=2))
        lines = []
        for i, t in enumerate(args.get("todos", []), 1):
            mark = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}.get(t.get("status"), "[ ]")
            lines.append(f"{i}. {mark} {t.get('content', '')}")
        return {"ok": True, "output": "todos saved:\n" + "\n".join(lines), "error": ""}
    return await asyncio.to_thread(_run)


async def _tool_skill(args: dict) -> dict:
    """Skill — lazily load a SKILL.md package from the workspace."""
    def _run():
        mode = args.get("mode", "load")
        name = args.get("name", "")
        skills_root = WORKSPACE / "skills"
        if mode == "list":
            if not skills_root.exists(): return {"ok": True, "output": "(no skills/ directory)", "error": ""}
            rows = []
            for d in sorted(skills_root.iterdir(), key=lambda x: x.name.lower()):
                if not d.is_dir() or d.name.startswith("_"): continue
                sm = d / "SKILL.md"
                if not sm.exists(): continue
                rows.append(f"  {d.name}")
            return {"ok": True, "output": "Installed skills:\n" + ("\n".join(rows) if rows else "(none)"), "error": ""}
        if not name: return {"ok": False, "error": "name required (or mode='list')", "output": ""}
        skill_md = skills_root / name / "SKILL.md"
        if not skill_md.exists():
            available = sorted([d.name for d in skills_root.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]) if skills_root.exists() else []
            return {"ok": False, "error": f"skill '{name}' not found", "output": f"Available: {available}" if available else "(none)"}
        content = skill_md.read_text(encoding="utf-8", errors="replace")
        subdirs = sorted([d.name for d in (skills_root / name).iterdir() if d.is_dir()])
        files = sorted([f.name for f in (skills_root / name).iterdir() if f.is_file() and f.name != "SKILL.md"])
        return {"ok": True, "output": f"# Skill: {name}\nSubdirs: {subdirs}\nFiles: {files}\n\n---\n\n{content}", "error": ""}
    return await asyncio.to_thread(_run)


TOOLS_MAP = {
    "Bash": _tool_bash, "Read": _tool_read, "Write": _tool_write, "Edit": _tool_edit,
    "Glob": _tool_glob, "Grep": _tool_grep, "LS": _tool_ls, "TodoWrite": _tool_todowrite,
    "Skill": _tool_skill,
}


def to_openai_tools() -> list[dict]:
    return [
        {"type": "function", "function": {"name": "Bash", "description": "Execute a bash command in your workspace. Full Linux (Termux). You can install packages (pkg/pip/npm), run scripts, git, anything.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer", "default": 120}}, "required": ["command"]}}},
        {"type": "function", "function": {"name": "Read", "description": "Read a text file. Returns cat -n style.", "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "offset": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 2000}}, "required": ["file_path"]}}},
        {"type": "function", "function": {"name": "Write", "description": "Create or overwrite a file.", "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}, "required": ["file_path", "content"]}}},
        {"type": "function", "function": {"name": "Edit", "description": "Exact string replacement.", "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "old_str": {"type": "string"}, "new_str": {"type": "string"}, "replace_all": {"type": "boolean", "default": False}}, "required": ["file_path", "old_str", "new_str"]}}},
        {"type": "function", "function": {"name": "Glob", "description": "Find files by name pattern.", "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string", "default": "."}}, "required": ["pattern"]}}},
        {"type": "function", "function": {"name": "Grep", "description": "Search file contents with ripgrep.", "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string", "default": "."}, "ignore_case": {"type": "boolean", "default": False}}, "required": ["pattern"]}}},
        {"type": "function", "function": {"name": "LS", "description": "List directory contents.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "TodoWrite", "description": "Update your todo list.", "parameters": {"type": "object", "properties": {"todos": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}, "priority": {"type": "string", "enum": ["high", "medium", "low"]}}, "required": ["id", "content", "status", "priority"]}}}, "required": ["todos"]}}},
        {"type": "function", "function": {"name": "Skill", "description": "Load a SKILL.md package. mode='list' to see all, mode='load' name='X' to read one.", "parameters": {"type": "object", "properties": {"mode": {"type": "string", "enum": ["list", "load", "read"], "default": "load"}, "name": {"type": "string"}, "file": {"type": "string"}}, "required": []}}},
    ]


# --------------------------------------------------------------------------- #
# Session + agent loop
# --------------------------------------------------------------------------- #
class Session:
    def __init__(self, base_url: str, api_key: str, model: str, session_id: str = ""):
        self.session_id = session_id or uuid.uuid4().hex[:16]
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.messages: list[dict] = []
        self.iterations = 0
        self.started_at = time.time()
        self.max_iterations = 25


def _system_prompt() -> str:
    return f"""You are PocketAgent — a personal AI agent running inside your own Linux computer (Termux on the user's phone).

# What you are
- You live in a real Linux workspace at {WORKSPACE}
- Layout: download/ (deliverables), scripts/ (your scripts), upload/ (user files), skills/ (SKILL.md packages)
- You have FULL Linux — pkg (Termux package manager), pip, npm, git, curl, anything

# Tools
- Bash: run any command (full Linux)
- Read/Write/Edit: file operations
- Glob/Grep: find files / search content
- LS: list dirs
- TodoWrite: track your tasks
- Skill: load modular skill packages

# How you work
- ALWAYS make a todo list first for multi-step tasks
- Persist scripts to scripts/ before running
- Save deliverables to download/
- Be autonomous — install tools if you need them (pkg install, pip install)
- Stream your thinking as you work; the user is watching on their phone
- Match the user's language
- When done, give a brief summary (≤100 words)

You are powerful. Take initiative."""


async def run_agent_loop(session: Session, user_message: str) -> AsyncIterator[dict]:
    """Run one full agent turn. Yields events."""
    def _evt(t, **kw): return {"type": t, "ts": time.time(), **kw}

    yield _evt("user.message", content=user_message)
    session.messages.append({"role": "user", "content": user_message})

    if not any(m.get("role") == "system" for m in session.messages):
        session.messages.insert(0, {"role": "system", "content": _system_prompt()})

    tools = to_openai_tools()

    while session.iterations < session.max_iterations:
        session.iterations += 1
        assistant_text = ""
        tool_calls: list[dict] = []

        try:
            async with httpx.AsyncClient(timeout=300) as c:
                async with c.stream("POST", f"{session.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {session.api_key}", "Content-Type": "application/json"},
                        json={"model": session.model, "messages": session.messages, "tools": tools, "stream": True, "max_tokens": 8000}) as r:
                    if r.status_code != 200:
                        body = await r.aread()
                        yield _evt("error", message=f"LLM error {r.status_code}: {body.decode()[:300]}", kind="llm")
                        return
                    async for line in r.aiter_lines():
                        if not line or not line.startswith("data: "): continue
                        data = line[6:]
                        if data == "[DONE]": break
                        try:
                            chunk = json.loads(data)
                            if not chunk.get("choices"): continue
                            delta = chunk["choices"][0].get("delta", {})
                            if delta.get("content"):
                                assistant_text += delta["content"]
                                yield _evt("assistant.delta", content=delta["content"])
                            if delta.get("tool_calls"):
                                for tc in delta["tool_calls"]:
                                    idx = tc["index"]
                                    while len(tool_calls) <= idx: tool_calls.append({"id": "", "name": "", "args": ""})
                                    if tc.get("id"): tool_calls[idx]["id"] = tc["id"]
                                    if tc.get("function", {}).get("name"): tool_calls[idx]["name"] = tc["function"]["name"]
                                    if tc.get("function", {}).get("arguments"): tool_calls[idx]["args"] += tc["function"]["arguments"]
                        except: pass
        except Exception as e:
            yield _evt("error", message=f"LLM error: {type(e).__name__}: {e}", kind="llm")
            return

        # Assemble assistant message
        if tool_calls:
            msg = {"role": "assistant", "content": assistant_text or None,
                   "tool_calls": [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["args"]}} for tc in tool_calls]}
        else:
            msg = {"role": "assistant", "content": assistant_text}
        session.messages.append(msg)

        if assistant_text:
            yield _evt("assistant.message", content=assistant_text)

        if not tool_calls:
            yield _evt("session.end", reason="complete", iterations=session.iterations)
            return

        # Execute tools
        for tc in tool_calls:
            call_id = tc["id"] or f"call_{uuid.uuid4().hex[:8]}"
            name = tc["name"]
            try:
                args = json.loads(tc["args"]) if tc["args"] else {}
            except json.JSONDecodeError as e:
                args = {}
                yield _evt("tool.call", call_id=call_id, name=name, args=args)
                yield _evt("tool.result", call_id=call_id, name=name, ok=False, output="", error=f"bad JSON: {e}", duration_ms=0)
                continue

            yield _evt("tool.call", call_id=call_id, name=name, args=args)
            t0 = time.time()
            tool_fn = TOOLS_MAP.get(name)
            if tool_fn is None:
                result = {"ok": False, "error": f"unknown tool: {name}", "output": ""}
            else:
                result = await tool_fn(args)
            duration_ms = int((time.time() - t0) * 1000)
            yield _evt("tool.result", call_id=call_id, name=name, ok=result["ok"], output=result["output"], error=result["error"], duration_ms=duration_ms)

            if name == "TodoWrite" and args.get("todos"):
                yield _evt("todo.update", todos=args["todos"])

            session.messages.append({"role": "tool", "tool_call_id": call_id, "content": (result["error"] + "\n" + result["output"]) if result["error"] else result["output"]})

    yield _evt("warning", message=f"max_iterations={session.max_iterations} reached")
    yield _evt("session.end", reason="max_iterations", iterations=session.iterations)


# --------------------------------------------------------------------------- #
# WebSocket
# --------------------------------------------------------------------------- #
@app.websocket("/agent")
async def agent_ws(ws: WebSocket):
    await ws.accept()

    # First frame = session.start with BYOK config
    try:
        start_frame = await ws.receive_json()
    except WebSocketDisconnect:
        return

    if start_frame.get("type") != "session.start":
        await ws.send_json({"type": "error", "message": "first frame must be session.start", "kind": "protocol"})
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    cfg = start_frame.get("session", {}) or {}
    if not cfg.get("api_key"):
        await ws.send_json({"type": "error", "message": "no api_key in session config (BYOK required)", "kind": "config"})
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    session = Session(
        base_url=cfg.get("base_url", "https://api.openai.com/v1"),
        api_key=cfg["api_key"],
        model=cfg.get("model", "gpt-4o-mini"),
        session_id=start_frame.get("resume_session_id") or "",
    )

    await ws.send_json({"type": "session.start", "session_id": session.session_id, "workspace": str(WORKSPACE), "model": session.model, "base_url": session.base_url})

    # Pending question futures (for AskUserQuestion — not yet implemented but stub here)
    current_task: Optional[asyncio.Task] = None

    try:
        while True:
            try:
                msg = await ws.receive_json()
            except WebSocketDisconnect:
                break

            mtype = msg.get("type")
            if mtype == "user.message":
                content = msg.get("content", "").strip()
                if not content: continue
                if current_task and not current_task.done():
                    current_task.cancel()
                    try: await current_task
                    except asyncio.CancelledError: pass

                async def _run_turn():
                    try:
                        async for evt in run_agent_loop(session, content):
                            await ws.send_json(evt)
                    except asyncio.CancelledError:
                        await ws.send_json({"type": "session.end", "reason": "cancelled", "iterations": session.iterations})
                    except Exception as e:
                        await ws.send_json({"type": "error", "message": f"{type(e).__name__}: {e}", "kind": "server"})

                current_task = asyncio.create_task(_run_turn())

            elif mtype == "ping":
                await ws.send_json({"type": "pong", "ts": time.time()})

            elif mtype == "session.reset":
                if current_task and not current_task.done():
                    current_task.cancel()
                    try: await current_task
                    except asyncio.CancelledError: pass
                session.messages = [m for m in session.messages if m.get("role") == "system"]
                session.iterations = 0
                await ws.send_json({"type": "session.reset.ack", "session_id": session.session_id})

            else:
                await ws.send_json({"type": "error", "message": f"unknown frame: {mtype}", "kind": "protocol"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try: await ws.send_json({"type": "error", "message": f"{type(e).__name__}: {e}", "kind": "server"})
        except: pass
    finally:
        if current_task and not current_task.done():
            current_task.cancel()
            try: await current_task
            except asyncio.CancelledError: pass
