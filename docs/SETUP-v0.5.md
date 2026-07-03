# PocketAgent v0.5 — Setup Guide

## What changed in v0.5

**No more cloud.** The agent runtime now runs inside **Termux** on your phone. The APK is a thin UI that connects to `localhost:8080`. This means:
- ❌ No GitHub Codespaces
- ❌ No Hugging Face Spaces
- ❌ No Daytona
- ❌ No Render
- ❌ No credit card anywhere
- ✅ Full Linux (Termux) on your phone
- ✅ LLM key never leaves your phone
- ✅ Persistent workspace
- ✅ Works offline (tools still run; only LLM needs internet)

---

## Setup (3 steps, ~5 minutes)

### Step 1: Install Termux

Download Termux from **F-Droid** (not Play Store — the Play Store version is outdated):

👉 https://f-droid.org/packages/com.termux/

Open Termux after installing.

### Step 2: Install the PocketAgent runtime

In Termux, run these commands:

```bash
pkg update -y
pkg install python git ripgrep -y
pip install pocketagent-runtime
pocketagent-start
```

You should see:
```
🚀 Starting PocketAgent runtime on port 8080...
✅ PocketAgent is running on http://127.0.0.1:8080
   Open the PocketAgent app on your phone to connect.
```

**Leave Termux running** (don't close it). The runtime stays alive as long as Termux is open.

### Step 3: Install + set up the PocketAgent APK

1. Download `PocketAgent-v0.5.0.apk` from the GitHub release
2. Install it (allow "unknown sources" if prompted)
3. Open the app → complete onboarding:
   - Pick your LLM provider (OpenAI/z.ai/Anthropic/Gemini/OpenRouter/Groq/Mistral/Custom)
   - Paste your API key
   - Tap **Fetch** to pick a model from the list
   - Tap **Test** to verify the connection works
   - Finish
4. The app detects the Termux runtime automatically → tap **Connect**
5. Chat with your agent 🎉

---

## How it works

```
┌─────────────────────────────────┐
│  PocketAgent APK (thin UI)      │
│  - Chat interface               │
│  - Shows agent thinking/steps   │
│  - File viewer                  │
│  - Settings (LLM key, etc.)     │
│                                 │
│  Connects via:                  │
│  ws://127.0.0.1:8080/agent      │
└──────────────┬──────────────────┘
               │ localhost (no internet needed)
               ▼
┌─────────────────────────────────┐
│  Termux (the agent's computer)  │
│                                 │
│  pocketagent-runtime running:   │
│  - FastAPI + WebSocket server   │
│  - Full agent loop              │
│  - All 9 tools (Bash/Read/...)  │
│                                 │
│  Workspace: ~/pocketagent-      │
│  workspace/                     │
│    ├── download/                │
│    ├── scripts/                 │
│    ├── upload/                  │
│    └── skills/                  │
│                                 │
│  Calls YOUR LLM directly:       │
│  → api.openai.com               │
│  → api.z.ai                     │ │
│  → api.gateway.orgn.com         │  └── phone's internet
│  → (whatever you configured)    │
└─────────────────────────────────┘
```

---

## Tips

### Keep Termux alive in background
Android may kill Termux when in background. To prevent this:
1. Install **Termux:API** from F-Droid
2. In Termux, run: `pkg install termux-api`
3. The runtime automatically acquires `termux-wake-lock` on start

### View runtime logs
```bash
cat ~/.pocketagent/runtime.log
```

### Stop the runtime
```bash
pocketagent-stop
```

### Check if running
```bash
pocketagent-status
```

### Access workspace files from Android
The workspace is at `~/pocketagent-workspace/` inside Termux. To access from Android:
```bash
termux-setup-storage  # one-time, gives Termux access to /sdcard/
cp -r ~/pocketagent-workspace/download/* /sdcard/Download/
```

### Use a different LLM
Open the PocketAgent app → Settings → change provider/key/model → Save → reconnect.

---

## Troubleshooting

### "Runtime not detected" in the app
- Make sure Termux is open and `pocketagent-start` was run
- Run `pocketagent-status` in Termux to verify
- Check `curl http://127.0.0.1:8080/` in Termux returns JSON

### "Connection failed"
- Make sure both Termux AND the PocketAgent app are running
- The app connects to `127.0.0.1:8080` — both must be on the same device
- Try: `pocketagent-stop && pocketagent-start`

### LLM errors
- Check your API key in Settings
- Tap "Test connection" to verify
- Check your LLM provider's credit balance

### Tool errors (Bash/Read/Write)
- All tools run in `~/pocketagent-workspace/`
- The agent can't write outside this directory (sandboxed)
- For ripgrep: `pkg install ripgrep` (already in setup instructions)
