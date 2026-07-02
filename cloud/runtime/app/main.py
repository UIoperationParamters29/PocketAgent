"""PocketAgent FastAPI app — the cloud's front door.

Two endpoints:
  GET  /              → health + version
  GET  /workspace     → JSON snapshot of the workspace tree (for the phone's file explorer)
  WS   /agent         → the main streaming channel (phone ↔ agent)

Auth: Bearer token in `Authorization` header (or first WS frame), matching
settings.channel_secret. If channel_secret is empty (local dev), auth is skipped.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .agent import Session, run_agent_loop
from .config import settings


# --------------------------------------------------------------------------- #
# Lifespan
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure workspace dirs exist (also done in Settings validator, but double-safe)
    for sub in ("download", "scripts", "upload", "skills", ".pocketagent"):
        (settings.workspace_root / sub).mkdir(parents=True, exist_ok=True)
    # Generate an ephemeral channel secret if none set
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

# CORS — wide open (the phone connects from anywhere; auth is via channel_secret)
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
    """Return a JSON snapshot of the workspace tree for the phone's file explorer."""
    root = settings.workspace_root.resolve()

    def build(p: Path, d: int) -> dict[str, Any]:
        node: dict[str, Any] = {"name": p.name or str(p), "path": str(p.relative_to(root)) if p != root else "", "type": "dir" if p.is_dir() else "file"}
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
          "session": {
            "base_url": "https://api.openai.com/v1",   # BYOK endpoint
            "api_key":  "sk-...",                       # BYOK key — NEVER stored
            "model":    "gpt-4o-mini"
          },
          "resume_session_id": null                     # or a previous session_id
        }

    Then phone sends `{"type": "user.message", "content": "..."}` frames.
    Server streams events back. Phone can send further user.message frames
    to continue the conversation (session.messages accumulates).
    """
    # ----- Auth -----
    # Check header first (some WS clients can set it)
    auth = ws.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth else ""
    await ws.accept()

    if settings.channel_secret and token != settings.channel_secret:
        # Allow auth via first frame instead
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
    # BYOK: the phone MUST send an api_key. We do NOT silently fall back to
    # the server's default_api_key (which is for local dev only) — that would
    # mask a real misconfiguration on the phone.
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

    await ws.send_json({
        "type": "session.start",
        "session_id": session.session_id,
        "workspace": str(settings.workspace_root),
        "model": session.model,
        "base_url": session.base_url,
        "resumed": resume_id is not None,
    })

    # ----- Main loop -----
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
                # Stream all events from the agent loop
                async for evt in run_agent_loop(session, content):
                    await ws.send_json(evt)
            elif mtype == "ping":
                await ws.send_json({"type": "pong", "ts": __import__("time").time()})
            elif mtype == "session.reset":
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
