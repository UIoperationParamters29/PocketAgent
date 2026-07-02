# Cloud runtime

The cloud runtime is the FastAPI + WebSocket server that runs inside the codespace and serves as the agent's "brain + hands."

## Layout

```
runtime/
├── app/
│   ├── __init__.py
│   ├── main.py          ← FastAPI app, /agent WebSocket endpoint
│   ├── agent.py         ← the streaming agent loop (LLM + tools)
│   ├── config.py        ← Settings (env-driven via PA_* vars)
│   └── tools/
│       ├── __init__.py
│       └── registry.py  ← the 8 z.ai-parity tools
├── tests/
│   ├── test_smoke.py    ← 6 tests, no API key needed
│   └── test_live.py     ← full WS integration test (mocked LLM)
└── pyproject.toml
```

## Run

```bash
pip install -e .
python tests/test_smoke.py    # 6 tests, no API key
python tests/test_live.py     # full WS integration
uvicorn app.main:app --reload # http://localhost:8000
```

## Env vars

| Var | Required | Default | Purpose |
|---|---|---|---|
| `PA_HOST` | no | `0.0.0.0` | bind host |
| `PA_PORT` | no | `8000` | bind port |
| `PA_CHANNEL_SECRET` | **yes (prod)** | (ephemeral) | shared secret for phone↔cloud auth |
| `PA_WORKSPACE_ROOT` | no | `/home/z/my-project` or `./workspace` | the agent's "own computer" |
| `PA_DEFAULT_API_KEY` | no | `""` | local dev only — production uses per-session BYOK |
| `PA_DEFAULT_MODEL` | no | `gpt-4o-mini` | default model name |
| `PA_DEFAULT_BASE_URL` | no | `https://api.openai.com/v1` | default OpenAI-compatible endpoint |
| `PA_MAX_ITERATIONS` | no | `25` | tool-call loop cap |
| `PA_BASH_TIMEOUT_S` | no | `120` | per-Bash-command timeout |
| `PA_LOG_LEVEL` | no | `INFO` | DEBUG/INFO/WARNING/ERROR |
