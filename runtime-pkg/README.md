# PocketAgent Runtime

The agent's own Linux computer. Runs inside **Termux** on your Android phone.

## Install

```bash
# In Termux:
pkg install python git ripgrep -y
pip install pocketagent-runtime
pocketagent-start
```

That's it. The runtime is now running on `http://127.0.0.1:8080` inside Termux. Open the PocketAgent app on your phone to connect.

## What it does

- Runs a FastAPI + WebSocket server on `127.0.0.1:8080`
- The phone APK connects to `ws://127.0.0.1:8080/agent`
- The agent calls YOUR LLM (BYOK key sent from the phone)
- Executes tools (Bash, Read, Write, Edit, Glob, Grep, LS, TodoWrite, Skill) in `~/pocketagent-workspace/`
- Streams events (tokens, tool calls, results) back to the phone

## CLI

```bash
pocketagent-start    # start the runtime (foreground, with wake-lock)
pocketagent-stop     # stop a running runtime
pocketagent-status   # check if running
```

## Workspace

```
~/pocketagent-workspace/
├── download/      # final deliverables (documents, charts, scripts)
├── scripts/       # persisted generation scripts
├── upload/        # files uploaded from the phone
├── skills/        # modular SKILL.md packages
└── .pocketagent/  # internal state (todos, etc.)
```

## Why Termux?

- ✅ Full Linux (bash, python, node, git, pip, npm)
- ✅ App-private storage (no Android permission hell)
- ✅ Network access (calls your LLM directly)
- ✅ Persistent (survives app restarts)
- ✅ Free, no CC, no cloud
- ✅ Private (LLM key never leaves phone)
