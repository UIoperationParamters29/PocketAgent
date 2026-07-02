# Phone ↔ Cloud Event Protocol

The WebSocket channel at `/agent` uses JSON frames. Every frame has at least `{type, ts}`. This document is the contract — keep it stable.

## Handshake

The phone connects to `wss://<codespace>-8000.app.github.dev/agent` and immediately sends:

```json
{
  "type": "session.start",
  "channel_secret": "<PA_CHANNEL_SECRET>",
  "session": {
    "base_url": "https://api.openai.com/v1",
    "api_key":  "sk-...",
    "model":    "gpt-4o-mini"
  },
  "resume_session_id": null
}
```

Server replies:

```json
{
  "type": "session.start",
  "session_id": "37c359700c3a4051",
  "workspace": "/home/z/my-project",
  "model": "gpt-4o-mini",
  "base_url": "https://api.openai.com/v1",
  "resumed": false
}
```

Errors during handshake use `{"type":"error","kind":"auth|config|protocol","message":"..."}` and close the socket with code 1008.

## Phone → Server frames

| `type` | fields | purpose |
|---|---|---|
| `session.start` | see above | handshake |
| `user.message` | `content: string` | run one agent turn |
| `session.reset` | — | clear non-system messages, reset iteration counter |
| `ping` | — | server replies `pong` |

## Server → Phone events

Every event includes `ts` (unix seconds, float).

| `type` | fields | meaning |
|---|---|---|
| `session.start` | `session_id, workspace, model, base_url, resumed` | handshake ack |
| `user.message` | `content` | echo of the user's input |
| `assistant.delta` | `content` | one streamed token from the LLM (concatenate for live display) |
| `assistant.message` | `content` | the full assistant message once it's done streaming |
| `tool.call` | `call_id, name, args` | the LLM is calling a tool |
| `tool.result` | `call_id, name, ok, output, error, duration_ms` | the tool finished |
| `todo.update` | `todos[]` | the agent updated its todo list |
| `warning` | `message` | non-fatal issue (e.g. hit max_iterations) |
| `error` | `message, kind` | fatal issue for this turn |
| `session.end` | `reason, total_ms, iterations` | the turn is complete |

### `reason` values for `session.end`

- `complete` — LLM produced a final message with no further tool calls
- `max_iterations` — hit the 25-iteration cap (warning event precedes this)

### `kind` values for `error`

- `auth` — bad channel_secret
- `config` — missing api_key or other session config
- `protocol` — unknown frame type or wrong order
- `llm` — the LLM call itself failed (rate limit, bad key, etc.)
- `server` — unexpected server exception

## Example: a simple "list files" turn

```jsonl
→ {"type":"session.start","channel_secret":"...","session":{"api_key":"sk-...","model":"gpt-4o-mini","base_url":"https://api.openai.com/v1"}}
← {"type":"session.start","session_id":"abc123","workspace":"/home/z/my-project","model":"gpt-4o-mini","base_url":"https://api.openai.com/v1","resumed":false}
→ {"type":"user.message","content":"list the files in download/"}
← {"type":"user.message","content":"list the files in download/","ts":...}
← {"type":"tool.call","call_id":"call_1","name":"Bash","args":{"command":"ls -la download/"},"ts":...}
← {"type":"tool.result","call_id":"call_1","name":"Bash","ok":true,"output":"total 8\ndrwxr-xr-x 2 z z 4096 ...\n-rw-r--r-- 1 z z   22 ... report.pdf\n","error":"","duration_ms":42,"ts":...}
← {"type":"assistant.delta","content":"I","ts":...}
← {"type":"assistant.delta","content":" found","ts":...}
← {"type":"assistant.delta","content":" one","ts":...}
← {"type":"assistant.delta","content":" file","ts":...}
← {"type":"assistant.delta","content":" in","ts":...}
← {"type":"assistant.delta","content":" download","ts":...}
← {"type":"assistant.delta","content":"/:","ts":...}
← {"type":"assistant.delta","content":" report","ts":...}
← {"type":"assistant.delta","content":".pdf","ts":...}
← {"type":"assistant.message","content":"I found one file in download/: report.pdf","ts":...}
← {"type":"session.end","reason":"complete","total_ms":1842,"iterations":1,"ts":...}
```

## UI rendering suggestions (for the phone app)

- `assistant.delta` → append to the current assistant bubble (live typing effect)
- `assistant.message` → finalize the bubble (replace the deltas)
- `tool.call` → render a collapsible card titled "🔧 Bash" with the command preview
- `tool.result` → expand the card with the output (truncated to first 500 chars with "show more")
- `todo.update` → render a checklist above the chat scroll (sticky)
- `session.end` → un-disable the input box
- `error` → red toast; `kind=llm` should suggest checking the BYOK key
