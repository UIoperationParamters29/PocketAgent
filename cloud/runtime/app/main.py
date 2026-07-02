"""PocketAgent FastAPI app — the cloud's front door.

Endpoints:
  GET  /              → health + version
  GET  /workspace     → JSON snapshot of the workspace tree (for the phone's file explorer)
  WS   /agent         → the main streaming channel (phone ↔ agent)

Auth: Bearer token in `Authorization` header (or first WS frame), matching
settings.channel_secret. If channel_secret is empty (local dev), auth is skipped.

Bidirectional flow:
  The agent loop and the WS reader run as concurrent tasks. The agent emits
  events via UserResponder.send_event (which writes to the WS). The WS reader
  handles user.message AND user.answer frames — the latter resolves futures
  that AskUserQuestion is awaiting.
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .agent import Session, UserResponder, run_agent_loop
from .config import settings


# --------------------------------------------------------------------------- #
# Lifespan
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    for sub in ("download", "scripts", "upload", "skills", ".pocketagent"):
        (settings.workspace_root / sub).mkdir(parents=True, exist_ok=True)
    if not settings.channel_secret:
        ephem = os.urandom(16).hex()
        settings.channel_secret = ephem
        print(f"[PocketAgent] No PA_CHANNEL_SECRET set. Ephemeral secret: {ephem}")
    yield


app = FastAPI(
    title="PocketAgent Runtime",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# HTTP endpoints
# --------------------------------------------------------------------------- #
@app.get("/")
async def root():
    return {
        "name": "PocketAgent Runtime",
        "version": __version__,
        "workspace": str(settings.workspace_root),
        "default_model": settings.default_model,
        "default_base_url": settings.default_base_url,
    }


@app.get("/workspace")
async def workspace_tree(depth: int = 3):
    """JSON snapshot of the workspace tree for the phone's file explorer."""
    root = settings.workspace_root.resolve()

    def build(p: Path, d: int) -> dict[str, Any]:
        node: dict[str, Any] = {
            "name": p.name or str(p),
            "path": str(p.relative_to(root)) if p != root else "",
            "type": "dir" if p.is_dir() else "file",
        }
        if p.is_dir() and d > 0:
            try:
                node["children"] = [build(c, d - 1) for c in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))]
            except PermissionError:
                node["children"] = []
        elif p.is_file():
            try:
                node["size"] = p.stat().st_size
            except OSError:
                node["size"] = 0
        return node

    return build(root, depth)


@app.get("/file")
async def read_file(path: str):
    """Read a single file's contents (for the phone's file viewer)."""
    from .tools.registry import _resolve_safe
    try:
        p = _resolve_safe(path, must_exist=True)
        if not p.is_file():
            return {"ok": False, "error": "not a file"}
        # Cap at 200KB for the phone viewer
        data = p.read_bytes()
        if len(data) > 200_000:
            return {"ok": True, "path": str(p), "truncated": True, "size": len(data), "content": data[:200_000].decode("utf-8", errors="replace")}
        return {"ok": True, "path": str(p), "truncated": False, "size": len(data), "content": data.decode("utf-8", errors="replace")}
    except (PermissionError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# Responder that writes to a WebSocket
# --------------------------------------------------------------------------- #
class WSResponder(UserResponder):
    """A UserResponder whose send_event writes JSON to a WebSocket."""

    def __init__(self, ws: WebSocket):
        super().__init__()
        self.ws = ws

    async def send_event(self, evt: dict[str, Any]) -> None:
        await self.ws.send_json(evt)


# --------------------------------------------------------------------------- #
# WebSocket — the main channel
# --------------------------------------------------------------------------- #
@app.websocket("/agent")
async def agent_ws(ws: WebSocket):
    """Phone ↔ agent streaming channel.

    Handshake (first frame from phone):
        {
          "type": "session.start",
          "channel_secret": "<matches PA_CHANNEL_SECRET>",
          "session": {"base_url": "...", "api_key": "...", "model": "..."},
          "resume_session_id": null
        }

    Then phone sends:
        {"type": "user.message", "content": "..."}    → starts a turn
        {"type": "user.answer", "question_id": "...", "answer": {...}}  → resolves AskUserQuestion
        {"type": "ping"}
        {"type": "session.reset"}
    """
    # ----- Auth -----
    auth = ws.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth else ""
    await ws.accept()

    if settings.channel_secret and token != settings.channel_secret:
        try:
            first = await ws.receive_json()
            if first.get("type") == "session.start" and first.get("channel_secret") == settings.channel_secret:
                token = settings.channel_secret
                start_frame = first
            else:
                await ws.send_json({"type": "error", "message": "bad channel_secret", "kind": "auth"})
                await ws.close(code=status.WS_1008_POLICY_VIOLATION)
                return
        except WebSocketDisconnect:
            return
        except Exception as e:
            await ws.send_json({"type": "error", "message": f"handshake failed: {e}", "kind": "auth"})
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    else:
        try:
            start_frame = await ws.receive_json()
        except WebSocketDisconnect:
            return

    if start_frame.get("type") != "session.start":
        await ws.send_json({"type": "error", "message": "first frame must be session.start", "kind": "protocol"})
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # ----- Build session -----
    cfg = start_frame.get("session", {}) or {}
    resume_id = start_frame.get("resume_session_id")
    sent_key = cfg.get("api_key", "")
    if not sent_key:
        await ws.send_json({"type": "error", "message": "no api_key in session config (BYOK required)", "kind": "config"})
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    session = Session(
        session_id=resume_id or Session().session_id,
        base_url=cfg.get("base_url", settings.default_base_url),
        api_key=sent_key,
        model=cfg.get("model", settings.default_model),
    )

    responder = WSResponder(ws)
    await ws.send_json({
        "type": "session.start",
        "session_id": session.session_id,
        "workspace": str(settings.workspace_root),
        "model": session.model,
        "base_url": session.base_url,
        "resumed": resume_id is not None,
    })

    # ----- Main loop: read frames, spawn agent turns, multiplex answers -----
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
                if not content:
                    continue
                # If a previous turn is still running, cancel it (user interrupted)
                if current_task and not current_task.done():
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass
                # Spawn the new turn as a background task
                async def _run_turn():
                    try:
                        async for evt in run_agent_loop(session, content, responder=responder):
                            await ws.send_json(evt)
                    except asyncio.CancelledError:
                        await ws.send_json({"type": "session.end", "reason": "cancelled", "iterations": session.iterations})
                        raise
                    except Exception as e:
                        await ws.send_json({"type": "error", "message": f"{type(e).__name__}: {e}", "kind": "server"})

                current_task = asyncio.create_task(_run_turn())

            elif mtype == "user.answer":
                qid = msg.get("question_id")
                answer = msg.get("answer", {})
                ok = responder.resolve(qid, answer)
                if not ok:
                    await ws.send_json({"type": "warning", "message": f"no pending question for id {qid}"})

            elif mtype == "ping":
                await ws.send_json({"type": "pong", "ts": __import__("time").time()})

            elif mtype == "session.reset":
                if current_task and not current_task.done():
                    current_task.cancel()
                    try: await current_task
                    except asyncio.CancelledError: pass
                session.messages = [m for m in session.messages if m.get("role") == "system"]
                session.iterations = 0
                await ws.send_json({"type": "session.reset.ack", "session_id": session.session_id})

            else:
                await ws.send_json({"type": "error", "message": f"unknown frame type: {mtype}", "kind": "protocol"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": f"{type(e).__name__}: {e}", "kind": "server"})
        except Exception:
            pass
    finally:
        responder.close()
        if current_task and not current_task.done():
            current_task.cancel()
            try: await current_task
            except asyncio.CancelledError: pass
