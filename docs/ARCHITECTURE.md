# Architecture

This document explains why PocketAgent is built the way it is. For the wire protocol, see [`PROTOCOL.md`](./PROTOCOL.md).

## Design principles

1. **z.ai parity by default.** The tool surface (`Bash, Read, Write, Edit, Glob, Grep, LS, TodoWrite`) and the workspace layout (`download/, scripts/, upload/, skills/, AGENTS.md`) intentionally mirror z.ai agentic mode. Anything z.ai's "Producer" can do, PocketAgent can do.
2. **BYOK everywhere.** The runtime never owns an LLM key. The phone sends `base_url + api_key + model` on WebSocket connect; the runtime holds the key in memory for the duration of the session and never logs or persists it.
3. **Free, no credit card.** GitHub Codespaces gives 120 core-hrs/mo + 15 GB persistent storage, recurring, no CC. The phone build pipeline is free via GitHub Actions. No paid service is required at any layer.
4. **Streaming-first.** Every event from the agent loop (thinking token, tool call, tool result) is streamed to the phone as it happens. The UX is "watch the agent work," not "submit-and-wait."
5. **The codespace IS the sandbox.** Rather than running a separate microVM sandbox (E2B/Daytona — both have one-time free credits that would run out), the agent runtime runs directly inside the codespace and executes Bash/Read/Write against the codespace's own filesystem. One Linux box, one bill (which is $0).

## Layer 1 — Cloud Linux: GitHub Codespaces

**Why Codespaces won the bake-off:**

| Need | Codespaces | Modal (runner-up) | E2B | Fly.io |
|---|---|---|---|---|
| Free, no CC | ✅ 120 core-hrs/mo recurring | ✅ $30/mo recurring credit | ⚠️ $100 one-time | ❌ CC required |
| Persistent storage | ✅ 15 GB survives stops | ✅ Volumes + Snapshots | ✅ but small | n/a |
| Full Ubuntu + sudo | ✅ | ❌ container-only | ✅ | ✅ |
| Public HTTPS endpoint | ✅ `*.app.github.dev` | ✅ `*.modal.run` | ✅ | ✅ |
| API control from phone | ✅ REST + gh CLI | ✅ Python/TS SDK | ✅ SDK | ✅ |
| Long-term free tier | ✅ stable since 2022 | ✅ healthy | ⚠️ credit burns out | ❌ killed 2024 |

**The one trade-off:** 120 core-hrs/mo ≈ 60 active hours at 2-core. Not 24/7. The wake-on-demand model (phone wakes codespace → agent works → auto-stops after 30 min idle) makes this ample for a personal agent.

**Persistent storage approach:**
- Primary = the codespace itself (15 GB). Survives idle stops.
- Belt-and-suspenders = git (the workspace is a repo; agent commits important artifacts).
- Secrets = Codespaces encrypted secrets (env vars injected at start, never on disk).

## Layer 2 — Agent runtime: FastAPI + WebSocket (this repo's `/cloud`)

The runtime is a single Python process running inside the codespace. It exposes:

- `GET /` — health check
- `GET /workspace?depth=N` — JSON snapshot of the workspace tree (for the phone's file explorer)
- `WS /agent` — the main streaming channel

### The agent loop (`app/agent.py`)

```
user.message frame
  │
  ▼
build messages array
  │
  ▼
call LLM (stream=True)  ────► assistant.delta events (token-by-token)
  │
  ▼
assemble assistant message
  │
  ├── no tool_calls? ──► session.end, done
  │
  ▼
for each tool_call:
  emit tool.call event
  run tool (async, in thread)
  emit tool.result event
  append tool_result to messages
  │
  ▼
loop back to "call LLM" (until max_iterations=25)
```

### Tool surface (`app/tools/registry.py`)

Each tool is a `ToolSpec(name, description, json_schema, run)`. The registry exports `to_openai_tools()` for the LLM and `call_tool(name, args)` for the loop. All tools are sandboxed to `workspace_root` — `_resolve_safe()` blocks any path escape.

| Tool | z.ai equivalent | Implementation |
|---|---|---|
| `Bash` | Bash | `subprocess.run(cmd, shell=True, cwd=workspace)` with timeout + output truncation |
| `Read` | Read | `Path.read_text()` with offset/limit, cat -n style output |
| `Write` | Write | `Path.write_text()` (parents auto-created) |
| `Edit` | Edit | exact string replace; non-unique `old_str` rejected unless `replace_all=true` |
| `Glob` | Glob | `Path.rglob()` + fnmatch |
| `Grep` | Grep | ripgrep via `ripgrepy` |
| `LS` | LS | `Path.iterdir()` with ignore patterns |
| `TodoWrite` | TodoWrite | persisted to `workspace/.pocketagent/todos.json` |

Coming in Phase 3: `Skill, Task (subagents), AskUserQuestion, Outline, Complete`.

### BYOK security model

1. Phone derives a passphrase-based KEK with Argon2id (local-only).
2. Phone stores the encrypted LLM API key in `expo-secure-store` (Android Keystore / iOS Keychain — hardware-backed).
3. On WebSocket connect, phone sends the plaintext key in the first frame over TLS.
4. Runtime holds the key in `Session.api_key` (in-memory only). It is never logged, never written to disk, never included in tool output.
5. When the WebSocket closes, the Session object is garbage-collected and the key is gone.

## Layer 3 — Phone app: React Native + Expo (Phase 2)

Not built yet. Planned stack:

- **RN + Expo SDK 52+** — true native, TypeScript, iOS-ready
- **`expo-secure-store`** — hardware-backed BYOK key storage
- **Vercel AI SDK `useChat`** — streaming chat with `toolInvocations` rendered as z.ai-style cards
- **WebView + xterm.js** — terminal viewer (read-mostly; input via native bar)
- **`FlashList`** — file explorer tree
- **GitHub Actions** — free APK build pipeline (Ubuntu runner, `expo prebuild` + Gradle)
- **Self-hosted `expo-open-ota`** — OTA updates without APK reinstall

Aesthetic: dark theme, JetBrains Mono, accent `#10a37f` (z.ai green). No crowding, modern, dynamic.

## Why not other approaches

- **Claude Computer Use / Kimi Computer / OpenAI Operator** — closed-source, not BYOK, not phone-targeted. Inspirations only.
- **Cline / Roo Code** — VS-Code-bound. Not a phone app.
- **AutoGen / CrewAI / LangGraph** — multi-agent orchestration frameworks, not "one agent with its own computer" runtimes. Too heavy for our use case.
- **E2B as primary backend** — $100 one-time credit burns out. Codespaces' recurring quota is sustainable.
- **PWA / TWA** — wrapped webview, worse smoothness than RN, weaker secure-storage story.
- **Tauri Mobile** — promising but no built-in OTA, heavier toolchain, smaller plugin ecosystem.

## Honest risks

- **Codespaces quota (120 core-hrs/mo)** — fine for on-demand personal use. Upgrade to GitHub Pro ($4/mo) for 180 core-hrs if needed.
- **Google 2026–2027 sideload verification** — free one-time developer KYC, doesn't kill sideloading.
- **RN streaming polyfill** — known version-compat bug between `expo@52` and `ai@4.2.8`. We'll pin versions and test streaming on a real device in Phase 2.
- **xterm.js touch support** — limited. Fine as a viewer; native input bar for typing.
- **Anthropic/Gemini native APIs** — not OpenAI-format. Phase 5 adds a LiteLLM sidecar to translate.
