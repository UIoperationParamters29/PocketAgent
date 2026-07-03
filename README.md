# PocketAgent

> BYOK AI agentic workspace on your phone. A faithful clone of z.ai agentic mode, cloud-backed by GitHub Codespaces, native phone app via Expo.

**Status:** Phase 0–1 complete. Cloud runtime is live-tested and verified. Phone app + Codespaces deployment next.

---

## What this is

PocketAgent gives you a personal AI agent that **has its own Linux computer** (a GitHub Codespace) and that you drive from a **native Android app** (Expo/React Native, iOS-ready). The agent is BYOK — you plug in your own API key for OpenAI, Anthropic, z.ai GLM, Gemini, OpenRouter, Groq, Mistral, or any OpenAI-compatible endpoint. The agent runs in a loop with a full tool surface that mirrors z.ai agentic mode: `Bash, Read, Write, Edit, Glob, Grep, LS, TodoWrite`. It writes files, installs packages, runs scripts — exactly like z.ai's "Producer" mode.

### Architecture (3 layers, all free, no credit card)

```
┌──────────────────────────────────────────────────────┐
│  PHONE (Android APK via Expo)                        │
│  - React Native + Expo SDK 52+                       │
│  - expo-secure-store for BYOK keys (Keystore-backed) │
│  - Vercel AI SDK useChat for streaming chat UI       │
│  - WebView+xterm.js for terminal/file viewer         │
└─────────────────────┬────────────────────────────────┘
                      │ WSS (TLS)
                      ▼
┌──────────────────────────────────────────────────────┐
│  CLOUD LINUX = GitHub Codespaces                     │
│  (the agent's "own computer")                        │
│  - 120 core-hrs/mo FREE, recurring. No CC.           │
│  - 15 GB persistent storage — survives stops.        │
│  - Full Ubuntu with sudo.                            │
│  - Public HTTPS port forwarding on :8000.            │
│  - REST API: phone wakes/stops it on demand.         │
│                                                      │
│  Inside the codespace runs the AGENT RUNTIME:        │
│  FastAPI + WebSocket server (this repo's /cloud).    │
│  - OpenAI-compatible BYOK (any provider)             │
│  - Tool surface: Bash/Read/Write/Edit/Glob/Grep/LS/  │
│    TodoWrite (z.ai parity)                           │
│  - Workspace layout: download/, scripts/, upload/,   │
│    skills/, AGENTS.md (z.ai parity)                  │
└─────────────────────┬────────────────────────────────┘
                      │ HTTPS (BYOK key in env var, never logged)
                      ▼
                USER'S LLM PROVIDER
```

For the full design rationale, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Repo layout

```
PocketAgent/
├── cloud/                     ← runs inside the Codespace
│   ├── .devcontainer/         ← Codespaces build recipe
│   │   ├── devcontainer.json
│   │   └── bootstrap.sh
│   └── runtime/               ← FastAPI + WebSocket agent runtime
│       ├── app/
│       │   ├── main.py        ← FastAPI app, /agent WebSocket
│       │   ├── agent.py       ← the streaming agent loop
│       │   ├── config.py      ← settings (env-driven)
│       │   └── tools/         ← the z.ai-parity tool surface
│       │       └── registry.py
│       ├── tests/             ← smoke + live integration tests
│       └── pyproject.toml
├── phone/                     ← (Phase 2) Expo/React Native app
├── skills/                    ← modular SKILL.md packages (Phase 4)
├── docs/
│   ├── ARCHITECTURE.md
│   └── PROTOCOL.md            ← the phone↔cloud event protocol
└── .github/workflows/         ← CI + APK build pipeline
```

---

## Quick start — cloud runtime (local dev)

```bash
cd cloud/runtime
python -m pip install -e .
python tests/test_smoke.py        # 6 tests, no API key needed
python tests/test_live.py         # full WS integration test
uvicorn app.main:app --reload     # http://localhost:8000
```

Required env vars (set in `.env` or shell):
```
PA_CHANNEL_SECRET="<any-strong-secret>"   # phone must send this on WS connect
PA_DEFAULT_API_KEY="<your-key>"           # for local dev only
PA_DEFAULT_MODEL="gpt-4o-mini"
PA_DEFAULT_BASE_URL="https://api.openai.com/v1"
```

## Quick start — Codespaces (production target)

1. Open the repo on GitHub → Code → Codespaces → Create.
2. The devcontainer auto-installs Python 3.12, Node 20, ripgrep, ffmpeg, fonts.
3. Inside the codespace:
   ```bash
   export PA_CHANNEL_SECRET="$(openssl rand -hex 16)"
   cd cloud/runtime && uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
4. The port 8000 forward URL (`https://<codespace>-8000.app.github.dev`) is what your phone app connects to.

---

## BYOK providers

The runtime is provider-agnostic. The phone sends `base_url + api_key + model` on connect. Verified-compatible:

| Provider | `base_url` | API |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | OpenAI |
| z.ai GLM | `https://api.z.ai/api/pallet/v1` | OpenAI |
| Anthropic | `https://api.anthropic.com/v1` | **Native** (auto-translated) |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta` | **Native** (auto-translated) |
| OpenRouter | `https://openrouter.ai/api/v1` | OpenAI |
| Groq | `https://api.groq.com/openai/v1` | OpenAI |
| Mistral | `https://api.mistral.ai/v1` | OpenAI |
| Ollama (local) | `http://10.0.2.2:11434/v1` | OpenAI |
| Custom | any OpenAI-compatible | OpenAI |

Anthropic and Gemini have their own native APIs that aren't OpenAI-format. The runtime's `app/llm.py` adapter detects the provider from the base_url and translates messages + tool schemas automatically — no separate LiteLLM proxy needed.

## Skills

The agent can lazily load modular `SKILL.md` packages from `skills/`. Each skill teaches the agent how to do something new. Pre-seeded skills:

| Skill | What it teaches |
|---|---|
| `charts` | Bar/line/pie/scatter/heatmap (matplotlib) + flowchart/mind map/org chart/architecture (Mermaid/Playwright) |
| `pdf` | ReportLab reports, Playwright creative posters, LaTeX/Tectonic academic papers, pypdf process, resumes |
| `docx` | Word document creation/editing via python-docx |
| `image-generation` | AI image generation from text prompts |
| `web-search` | Real-time web search via z.ai SDK or DuckDuckGo fallback |

Use the Skill tool with `mode='list'` to discover, `mode='load'` to read SKILL.md, `mode='read'` to drill into briefs/configs/scripts.

---

## Roadmap

- [x] **Phase 0** — Repo scaffold, devcontainer, runtime package skeleton
- [x] **Phase 1** — Cloud runtime: FastAPI + WS + 8 tools (z.ai parity) + BYOK + smoke + live tests
- [x] **Phase 2** — Phone app (Expo/React Native): streaming chat + tool-call cards + file/terminal viewer
- [x] **Phase 3** — Full z.ai tool surface: `Skill, Task (subagents), AskUserQuestion, Outline, Complete`
- [x] **Phase 4** — Modular skill system (lazy SKILL.md loader, 5 pre-seeded skills: charts, pdf, docx, image-generation, web-search)
- [x] **Phase 5** — Multi-provider BYOK (OpenAI/Anthropic/Gemini native + OpenRouter/Groq/Mistral/Ollama)
- [x] **Phase 6** — Polish: animated typing dots, code-block rendering, smoother expand/collapse, polished onboarding + files + settings
- [ ] **Phase 7** — Final APK build pipeline + self-hosted OTA updates + release
- [ ] **Phase 8** — End-to-end smoke test in real Codespaces + phone, ship

---

## License

MIT (see `LICENSE`). Build freely, ship freely.

## Acknowledgements

Heavily inspired by **z.ai agentic mode** (the producer/runtime model this clones), **Kimi's computer use**, and **Claude Computer Use**. Tool surface and workspace layout intentionally mirror z.ai's `/home/z/my-project` sandbox.
