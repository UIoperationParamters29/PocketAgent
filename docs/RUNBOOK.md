# PocketAgent — Runbook

Everything you need to install and use PocketAgent on your phone.

---

## 1. Get the APK

The signed release APK is built automatically by GitHub Actions and stored as a workflow artifact.

**To download the latest APK:**

1. Go to https://github.com/UIoperationParamters29/PocketAgent/actions/workflows/build-apk.yml
2. Click the most recent successful run ("Build Android APK").
3. Scroll to the bottom → "Artifacts" → download `pocketagent-apk`.
4. Unzip the downloaded file → `app-release.apk` is your installable APK.

Or, trigger a fresh build:
- Go to the workflow page → "Run workflow" button (requires repo write access).

The APK is signed with the project's release keystore (stored as GitHub Actions secrets). The signing key is **never** in the repo — it's only in the secrets store.

---

## 2. Install on your phone

1. Copy `app-release.apk` to your Android phone (USB, cloud drive, email, whatever).
2. On the phone, open the file manager → tap the APK → "Install".
3. If prompted, allow "Install from unknown sources" for your file manager.
4. Open the **PocketAgent** app from your app drawer.

> **Note on Google's 2026–2027 sideload verification:** Starting in 2027, Android will require a one-time free developer identity verification for sideloaded APKs globally. This doesn't kill sideloading — it just adds a KYC step. For now (2026), sideloading works as usual.

---

## 3. First-run setup (onboarding)

The app's onboarding has 2 steps:

### Step 1: GitHub PAT
- Create a Personal Access Token at https://github.com/settings/tokens/new
- Scopes required: `repo`, `codespace`, `workflow`
- Paste it in the app. The app verifies the scopes before continuing.
- The PAT is stored in `expo-secure-store` (Android Keystore, hardware-backed).

### Step 2: BYOK + channel secret
- **Pick your LLM provider** (9 presets):
  - OpenAI (default `gpt-4o-mini`)
  - z.ai GLM (`glm-4.6`)
  - Anthropic (`claude-3-5-sonnet-20241022`) — native API, auto-translated
  - Google Gemini (`gemini-1.5-pro`) — native API, auto-translated
  - OpenRouter, Groq, Mistral, Ollama (local), or Custom
- **Paste your API key** for that provider.
- **Generate a channel secret** (32-char hex) — this is the shared secret between your phone and the codespace runtime. **Save this value** — you'll set it as a Codespaces secret next.

---

## 4. Set the channel secret on GitHub

The codespace runtime needs the same `PA_CHANNEL_SECRET` you generated in the app.

1. Go to https://github.com/settings/codespaces
2. Scroll to "Codespace secrets" → "New secret"
3. Name: `PA_CHANNEL_SECRET`
4. Value: paste the 32-char hex you generated in the app
5. Select the repository: `UIoperationParamters29/PocketAgent`
6. Save.

This secret is automatically injected into any codespace created from the PocketAgent repo.

---

## 5. Create your PocketAgent codespace

The codespace is your agent's "own computer" — a real Ubuntu Linux box with 15 GB persistent storage.

1. Go to https://github.com/UIoperationParamters29/PocketAgent
2. Click the green "Code" button → "Codespaces" tab → "Create codespace on main".
3. Wait ~2–3 minutes for the codespace to provision. The `bootstrap.sh` script:
   - Installs Python 3.12 + Node 20 + ripgrep + ffmpeg + fonts
   - Installs the runtime (`pip install -e cloud/runtime`)
   - Starts uvicorn on port 8000 in the background
   - Writes a status file (`.codespace-status.md` in the repo working dir)
4. **The codespace must be opened in the browser/editor at least once** for GitHub to register the public port-forward URL. Open it once and the URL `https://<codespace-name>-8000.app.github.dev` will start working.

To check if the runtime is alive:
```bash
curl https://<your-codespace-name>-8000.app.github.dev/
# Should return: {"name":"PocketAgent Runtime", ...}
```

---

## 6. Use the app

1. Open PocketAgent on your phone.
2. On the Chat screen, tap **"Wake"** (top right). The app will:
   - Look up your codespace via the GitHub API
   - Start it if it's stopped
   - Wait for it to be Available
   - Derive the runtime URL: `https://<codespace-name>-8000.app.github.dev`
   - Connect via WebSocket
3. You'll see the status change: `Waking codespace…` → `Connecting…` → `Connected`.
4. Type a message and hit send. The agent will:
   - Stream its thinking token-by-token
   - Show tool calls as collapsible cards (Bash, Read, Write, Edit, etc.)
   - Show tool results inline
   - Update the todo list as it works
   - Ask you clarifying questions if needed (via the AskUserQuestion card)
5. Browse files your agent creates on the **Files** tab.
6. Edit your BYOK config on the **Settings** tab.

---

## 7. Tips and troubleshooting

### Codespace port returns 404
If `https://<codespace>-8000.app.github.dev/` returns 404:
- The codespace needs to be **opened in the browser/editor at least once** for the port forward to register. Open https://github.com/codespaces → click your codespace → wait for the editor to load.
- Or, in the codespace's terminal, run: `curl http://localhost:8000/` to verify uvicorn is running locally. If that returns 200 but the public URL returns 404, it's a port-forward registration issue (open the editor once).

### Codespace stops automatically
Codespaces auto-stop after 30 min of idle (configurable up to 4 hr). Your storage persists. Tap "Wake" in the app to restart it.

### Running out of free quota
GitHub Free gives 120 core-hours/month of codespace compute (~60 active hours at 2-core). For a personal agent used on-demand, this is plenty. If you need more, GitHub Pro ($4/mo) bumps it to 180 core-hours.

### Changing LLM provider
Open Settings → change provider/key/model/base_url → Save → disconnect+reconnect. The runtime is stateless per session — switching providers mid-conversation starts fresh.

### Wiping all data
Settings → "Wipe all data" removes PAT, channel secret, BYOK keys, and codespace name from the device. The codespace itself isn't deleted — go to github.com/codespaces to delete it.

---

## 8. Architecture (one-pager)

```
Phone (APK) ←WSS→ Cloud Linux (Codespaces) ←HTTPS→ LLM Provider
   │                  │
   │                  └─ Agent Runtime (FastAPI + WebSocket)
   │                     - 13 tools (z.ai parity)
   │                     - Provider adapter (OpenAI/Anthropic/Gemini)
   │                     - Workspace: download/, scripts/, upload/, skills/
   │
   └─ Stores: GitHub PAT, channel secret, BYOK key
      (expo-secure-store → Android Keystore)
```

See `docs/ARCHITECTURE.md` for the full design and `docs/PROTOCOL.md` for the wire format.
