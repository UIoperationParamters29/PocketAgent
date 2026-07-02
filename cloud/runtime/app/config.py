"""PocketAgent cloud agent runtime configuration.

All settings are loaded from environment variables (with sensible defaults).
Secrets (BYOK keys, session secrets) MUST be passed via environment, never
baked into the image or written to disk.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# The workspace is the agent's "own computer" — mirrors /home/z/my-project
# in the z.ai agentic sandbox. Layout:
#   workspace/
#     download/   ← final user-facing deliverables
#     scripts/    ← persisted generation scripts
#     upload/     ← files the user uploaded from phone
#     skills/     ← modular SKILL.md packages (lazy-loaded)
#     AGENTS.md   ← custom instructions, mirrors z.ai's pattern
DEFAULT_WORKSPACE = Path("/home/z/my-project") if Path("/home/z/my-project").exists() else Path("./workspace")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    # Shared secret for the phone<->cloud WSS channel. The phone must send this
    # in the `Authorization: Bearer <token>` header or in the first WS frame.
    # If empty, the runtime generates an ephemeral one at startup (printed once).
    channel_secret: str = ""

    # --- Workspace ---
    workspace_root: Path = DEFAULT_WORKSPACE

    # --- LLM (OpenAI-compatible — covers OpenAI, z.ai GLM, OpenRouter,
    #     Groq, Mistral, Together, Anyscale, local Ollama via /v1, etc.) ---
    # The runtime is provider-agnostic. The phone sends a per-session config
    # (base_url, api_key, model) on connect; the runtime never persists it.
    default_base_url: str = "https://api.openai.com/v1"
    default_model: str = "gpt-4o-mini"
    # Optional default key (for local dev only — production uses per-session keys)
    default_api_key: str = ""

    # --- Agent loop ---
    max_iterations: int = 25
    max_tool_output_chars: int = 30_000  # truncate huge outputs (e.g., big ls)
    bash_timeout_s: int = 120

    # --- Logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("workspace_root")
    @classmethod
    def _ensure_workspace(cls, v: Path) -> Path:
        v = v.resolve()
        for sub in ("download", "scripts", "upload", "skills"):
            (v / sub).mkdir(parents=True, exist_ok=True)
        return v


settings = Settings()  # type: ignore[call-arg]
