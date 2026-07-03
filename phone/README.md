# PocketAgent Phone App

React Native + Expo app — the phone-side UI for PocketAgent.

## Status

Phase 2 complete: source tree written, types match the cloud protocol, all UI components for the 13-tool surface implemented. APK build pipeline in `.github/workflows/build-apk.yml`.

## Stack

- **React Native + Expo SDK 52** — true native, TypeScript, iOS-ready
- **expo-secure-store** — BYOK keys in Android Keystore / iOS Keychain (hardware-backed)
- **zustand** — minimal state, no boilerplate
- **react-navigation bottom-tabs** — Chat / Files / Settings
- **WebSocket** — streaming events from the cloud runtime (no SSE polyfill issues)
- **Dark theme** — z.ai-inspired: `#0E0E10` background, `#10A37F` accent, JetBrains Mono for code

## Layout

```
phone/
├── App.tsx                    ← root, navigation, onboarding gate
├── app.json                   ← Expo config
├── package.json
├── tsconfig.json
├── babel.config.js
└── src/
    ├── theme/colors.ts        ← dark palette + typography
    ├── lib/
    │   ├── types.ts           ← wire-protocol types (mirrors docs/PROTOCOL.md)
    │   ├── secure-store.ts    ← BYOK key storage + provider presets
    │   ├── codespaces.ts      ← GitHub Codespaces API client
    │   └── agent-ws.ts        ← WebSocket client with keepalive + reconnect
    ├── state/store.ts         ← zustand store; consumes raw events into UI state
    ├── hooks/
    │   └── useAgentSession.ts ← high-level: connect / sendMessage / answerQuestion
    ├── components/index.tsx   ← MessageBubble, ToolCallCard, TodoList, QuestionCard,
    │                            OutlineCard, CompleteCard, SubagentCard, ChatInput,
    │                            StatusBar
    └── screens/
        ├── OnboardingScreen.tsx ← first-run: GitHub PAT + channel secret + BYOK
        ├── ChatScreen.tsx       ← main UI: top bar, chat history, side cards, input
        ├── FilesScreen.tsx      ← workspace file explorer (tree + file viewer)
        └── SettingsScreen.tsx   ← edit keys / codespace / session info / wipe
```

## Run locally

```bash
cd phone
npm install
npx expo start      # scan QR with Expo Go (Android/iOS)
```

## Build a sideloadable APK

Two paths — see `docs/ARCHITECTURE.md` § "Build pipeline" for full details.

### Path A — GitHub Actions (recommended, free)

1. Generate a release keystore locally:
   ```bash
   keytool -genkey -v -keystore release.keystore -alias pocketagent \
     -keyalg RSA -keysize 2048 -validity 10000
   ```
2. Base64-encode it and add as a GitHub secret `SIGNING_KEYSTORE_BASE64`.
3. Also add: `SIGNING_KEY_ALIAS`, `SIGNING_KEY_PASSWORD`, `SIGNING_STORE_PASSWORD`.
4. Push a tag `v0.1.0` or trigger the workflow manually from the Actions tab.
5. Download the signed APK from the workflow's artifact.

### Path B — Local build

```bash
cd phone
npm install
npx expo prebuild --platform android --no-install
cd android
./gradlew assembleRelease   # or assembleDebug
# → android/app/build/outputs/apk/release/app-release.apk
```

Requires JDK 17 + Android SDK command-line tools (no Android Studio needed).

## Supported BYOK providers

Pre-baked in `secure-store.ts`:

| Provider | base_url |
|---|---|
| OpenAI | `https://api.openai.com/v1` |
| z.ai GLM | `https://api.z.ai/api/pallet/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Ollama (local) | `http://10.0.2.2:11434/v1` |
| Custom | any OpenAI-compatible endpoint |

## Aesthetic

- Dark background `#0E0E10`, surface `#18181B`
- Accent z.ai green `#10A37F`
- JetBrains Mono for all code/tool output
- Tool cards color-coded by tool (Bash=green, Read/Write/Edit=blue, Grep/Glob=purple, Skill=lime, Task=orange, AskUserQuestion=pink, Outline=cyan, Complete=emerald)
- Single-column chat, no crowding, smooth LayoutAnimation on expand/collapse
