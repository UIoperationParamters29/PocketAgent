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
| `user.answer` | `question_id, answer` | answer to an `AskUserQuestion` (resolves the pending future) |
| `session.reset` | — | clear non-system messages, reset iteration counter |
| `ping` | — | server replies `pong` |

## Server → Phone events

Every event includes `ts` (unix seconds, float).

### Core streaming events

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

### Bidirectional / Phase 3 events

| `type` | direction | fields | meaning |
|---|---|---|---|
| `user.question` | server→phone | `question_id, questions[]` | the agent is asking the user a structured question (AskUserQuestion). Phone renders a card and replies with `user.answer`. |
| `outline.update` | server→phone | `document_type, sections[], design?` | the agent committed to an outline (Outline tool). Phone renders a roadmap card. |
| `session.complete` | server→phone | `project_type, summary` | the agent marked the project complete (Complete tool). Phone shows a completion card. |

### Subagent events (Task tool)

When the agent uses `Task` to spawn a subagent, every event from the subagent is re-emitted with a `subagent.` prefix so the phone can show them in a nested card. The lifecycle is:

| `type` | fields | meaning |
|---|---|---|
| `subagent.start` | `subagent_id, subagent_type, description, depth` | subagent spawned |
| `subagent.user.message` | `content, subagent_id` | the prompt given to the subagent |
| `subagent.assistant.delta` | `content, subagent_id` | streamed token from subagent |
| `subagent.assistant.message` | `content, subagent_id` | subagent's final message |
| `subagent.tool.call` | `call_id, name, args, subagent_id` | subagent calling a tool |
| `subagent.tool.result` | `call_id, name, ok, output, error, subagent_id` | subagent's tool result |
| `subagent.session.end` | `reason, subagent_id` | subagent turn done |
| `subagent.end` | `subagent_id, depth` | subagent fully cleaned up |

Subagent nesting is capped at depth 2 (parent → subagent → sub-subagent). Subagents do NOT have access to `Task, AskUserQuestion, Outline, Complete` (those are parent-only).

### `reason` values for `session.end`

- `complete` — LLM produced a final message with no further tool calls
- `max_iterations` — hit the iteration cap (warning event precedes this)
- `cancelled` — user sent a new message that interrupted the previous turn

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
... (more deltas) ...
← {"type":"assistant.message","content":"I found one file in download/: report.pdf","ts":...}
← {"type":"session.end","reason":"complete","total_ms":1842,"iterations":1,"ts":...}
```

## Example: AskUserQuestion bidirectional flow

```jsonl
→ {"type":"user.message","content":"write me a birthday card"}
← {"type":"user.message","content":"write me a birthday card","ts":...}
← {"type":"tool.call","call_id":"c1","name":"AskUserQuestion","args":{"questions":[{"question":"For whom?","header":"Recipient","type":"single","options":[...]}]},"ts":...}
← {"type":"user.question","question_id":"a1b2c3d4e5f6","questions":[{"question":"For whom?",...}],"ts":...}
→ {"type":"user.answer","question_id":"a1b2c3d4e5f6","answer":[{"header":"Recipient","answer":"mom"}]}
← {"type":"tool.result","call_id":"c1","name":"AskUserQuestion","ok":true,"output":"[{\"header\":\"Recipient\",\"answer\":\"mom\"}]","error":"","duration_ms":1234,"ts":...}
← {"type":"assistant.delta","content":"Dear","ts":...}
... (streamed birthday card text) ...
← {"type":"session.end","reason":"complete","ts":...}
```

## UI rendering suggestions (for the phone app)

- `assistant.delta` → append to the current assistant bubble (live typing effect)
- `assistant.message` → finalize the bubble (replace the deltas)
- `tool.call` → render a collapsible card titled "🔧 Bash" (or tool name) with the args preview
- `tool.result` → expand the card with the output (truncated to first 500 chars with "show more")
- `todo.update` → render a checklist above the chat scroll (sticky)
- `user.question` → render a question card with the options as tappable chips; on tap, send `user.answer`
- `outline.update` → render a roadmap card with sections listed
- `session.complete` → render a completion card with summary + any download/ file links
- `subagent.*` → render inside a nested card under the parent's Task tool-call card
- `session.end` → un-disable the input box
- `error` → red toast; `kind=llm` should suggest checking the BYOK key
