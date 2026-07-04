# Hugging Face Spaces as a Cloud Linux Host for PocketAgent

**Research date:** July 2026 · **Sources:** official HF docs (spaces-overview, spaces-sdks-docker,
spaces-gpus, manage-spaces), HF community forums (2025 threads), and 2026 pricing analyses.
Verified live via web search + page reader.

**Use case under test:** Phone app ↔ WebSocket ↔ FastAPI server in cloud Linux ↔ LLM API.
Requirements: full Linux (apt/pip), public HTTPS URL that works **without opening a browser**,
and persistent storage OR a sandbox that lasts 1–2+ days (not hours).

Current PocketAgent cloud layer is **GitHub Codespaces**. This report evaluates HF Spaces as an
alternative/backup host.

---

## TL;DR — Verdict

**Conditionally viable as a backup/secondary host, not a clear upgrade over Codespaces for the
primary.** HF Spaces free tier is genuinely free (no CC), gives full Linux via the Docker SDK,
exposes a public `https://<space>.hf.space` URL that auto-wakes on request and lasts **48 hours**
of inactivity (meets the "1–2+ days" bar), and can reach OpenAI/Anthropic APIs on port 443.

But three real frictions make it weaker than Codespaces for *this* agent runtime:

1. **Ephemeral disk** — free tier storage is wiped on every restart/sleep-wake (Codespaces keeps 15 GB).
2. **WebSocket proxy friction** — the HF edge proxy is Gradio-optimized; non-root FastAPI WS paths
   (exactly PocketAgent's `WS /agent`) have documented 404 "request never reaches the container" bugs.
3. **Outbound domain blocking** — HF is intentionally blocking "abuse-prone" external domains
   (Telegram/Facebook/WhatsApp/…); LLM API endpoints currently work, but the policy is expanding and
   is a latent breakage risk for a BYOK agent.

Recommendation: keep Codespaces as primary; add an **HF Docker Space as an optional second backend**
the phone can switch to. Architect for portability either way (external state store, proxy-ready,
keep-warm ping, WS-path fallback). Details below.

---

## 1. Free tier verification (2026)

| Question | Answer | Source |
|---|---|---|
| Still free? | ✅ Yes. "CPU Basic" tier = $0, recurring, lifetime. | HF spaces-overview docs; metacto/eesel 2026 pricing guides |
| Credit card required? | ❌ No CC required for free Hub or free CPU Spaces. CC only needed to *upgrade* hardware. | manage-spaces docs ("A payment card … is required to access upgrade your Space"); hackceleration 2026 review |
| CPU | 2 vCPU | spaces-overview hardware table |
| RAM | 16 GB | spaces-overview hardware table |
| Disk | 50 GB **non-persistent** (ephemeral) | spaces-overview docs |
| GPU | None on free CPU tier (ZeroGPU = 3.5 min/day shared H200, irrelevant here) | metacto 2026 guide |
| Concurrency | One running container per Space | community threads |

**Conclusion:** Free tier is alive and unchanged in structure for 2026. 2 vCPU / 16 GB / 50 GB is
more than enough headroom for the PocketAgent FastAPI runtime (it's a single Python process).

---

## 2. Persistence model

| Aspect | Behavior |
|---|---|
| Default storage | **Ephemeral.** "The data written on disk is lost whenever your Docker Space restarts." (spaces-sdks-docker) |
| Persistent storage | **Paid add-on.** Attach a "Storage Bucket" mounted at `/data` (runtime-only, not during build). Billed per-TB. |
| Free-tier workaround | Persist state to an HF Dataset repo via `huggingface_hub` (free, git-LFS), or to an external DB/S3. |
| Sleep trigger (free cpu-basic) | "If your Space runs on the default `cpu-basic` hardware, it will go to sleep if inactive for more than a set time (currently, **48 hours**)." (spaces-gpus docs) |
| Opt out of sleep? | ❌ **No** on free tier. "If you want your Space never to deactivate or if you want to set a custom sleep time, you need to upgrade [to paid hardware]." Custom sleep time is also paid-only; cpu-basic "cannot configure a custom sleep time." (manage-spaces) |
| Wake behavior | ✅ "Anyone visiting your Space will restart it automatically." (spaces-gpus) — an incoming HTTP/WS request wakes it. |
| Manual pause | Owner can `pause_space()` — a paused Space does **not** auto-wake; needs `restart_space()`. (manage-spaces) |

**Key win for the requirement:** the **48-hour** idle window satisfies "a sandbox that lasts 1–2+
days (not hours)." That's far more generous than Codespaces' default 30-min auto-stop. But note the
asymmetry: once it *does* sleep and wake, the container is recreated and the ephemeral disk is wiped
— so in-memory session state and any files not committed to git/an HF dataset are gone.

**Implication for PocketAgent:** the agent currently keeps `Session.messages` in process memory and
writes todos to `workspace/.pocketagent/todos.json`. On HF Spaces a sleep-wake cycle would lose both.
To survive, persist session state to an HF Dataset repo (free) keyed by `session_id`, and have the
phone send `resume_session_id` on reconnect (the protocol already supports this).

---

## 3. Docker SDK Space — Dockerfile, apt, WebSocket

### Custom Dockerfile + apt install
✅ Fully supported. `sdk: docker` in `README.md` YAML, then a standard `Dockerfile`. `RUN apt-get install …`
works at **build** time, `pip install` works at build and runtime. Constraints:
- Container runs as **UID 1000** (non-root). Must `RUN useradd -m -u 1000 user` and `USER user`.
- **No sudo at runtime.** Anything needing apt must be baked into the image at build.
- `COPY`/`ADD` must use `--chown=user`.

### Port / networking model
- **Only ONE port** is exposed to the outside (default `7860`, override via `app_port` in YAML).
- Multiple internal ports are fine (e.g., run Elasticsearch on 9200 internally); to expose several
  externally you'd put Nginx in front as a reverse proxy on the single exposed port.
- Outbound from the container is restricted (see §5).

### WebSocket support
⚠️ **Works, but with documented friction on non-Gradio FastAPI apps.**

- Gradio and Streamlit (which both use WS heavily) work out of the box.
- Chainlit WS works once the `websockets` package is in `requirements.txt`.
- **Raw FastAPI `@app.websocket("/path")` has a known 404 bug on HF Spaces** (forum thread #159865,
  Jun–Sep 2025): the WS upgrade is rejected with HTTP 404 at the edge proxy *before* reaching
  Uvicorn — container logs show the GET but never the WS attempt. Persists regardless of path
  (`/`, `/ws`, `/queue/join`). Related reports: "Docker Space POST endpoint 404 — routing never
  reaches FastAPI container" (Jul 2025) and "HF proxy stripping Access-Control headers" (Reddit).

**Direct relevance to PocketAgent:** the runtime's main channel is `WS /agent` — a non-root WS path
on a FastAPI app. This is precisely the configuration that hits the proxy 404. Mitigations to test:
- Serve WS on the root path (`/`) or verify the proxy forwards upgrades to `/agent`.
- Ensure `websockets` + `uvicorn[standard]` are pinned in the image.
- Worst case, front Uvicorn with a tiny Nginx that handles the upgrade, or fall back to SSE /
  long-poll on the HTTP path (the agent already streams JSON events; SSE is a small adapter).

---

## 4. Public URL behavior

| Question | Answer |
|---|---|
| URL format | `https://<space-subdomain>.hf.space` (e.g. `osanseviero-i-like-flan.hf.space`). Exposed via `SPACE_HOST` env var. |
| Works immediately on creation? | ✅ Yes, once the build finishes. A `curl https://<space>.hf.space/` returns the app response with no browser involved. |
| Works without opening a browser? | ✅ Yes — pure HTTP/S clients (curl, the phone app) work. No OAuth/login dance for **public** Spaces. |
| Auto-wakes on incoming request? | ✅ Yes. "Anyone visiting your Space will restart it automatically." First request triggers the cold start. |
| Private Spaces | Need `Authorization: Bearer hf_…` token on every request (fits PocketAgent's existing `channel_secret` model). |
| Protected Spaces (code private, app public) | Requires PRO/Team plan. |

**Conclusion:** the URL requirement is fully met — arguably cleaner than Codespaces' `*.app.github.dev`
because there's no port-forwarding/`gh codespace` setup; it's a stable, guessable-ish HTTPS endpoint
that the phone can hit directly.

---

## 5. Outbound internet (LLM API reachability)

**Official policy (spaces-overview):** "If your Space needs to make any network requests, you can
make requests through the standard HTTP and HTTPS ports (**80 and 443**) along with port **8080**.
Any requests going to other ports will be blocked."

**Reality on the ground (2025 forum evidence):**
- HF is **intentionally blocking specific external domains** at the DNS layer
  (`getaddrinfo ENOTFOUND`): confirmed for `api.telegram.org`, `graph.facebook.com`,
  `web.whatsapp.com`, `api.wit.ai`, and some Vercel-hosted endpoints.
- HF staff response (forum #175045): *"This is intended behavior, huggingface will start cracking
  down on external requests as the majority of users have been abusing it."*
- Isolated reports of intermittent `api.openai.com` connection errors (forum #160318), but the
  dominant pattern is that **OpenAI/Anthropic API calls from HF Spaces work** — it's an extremely
  common pattern (thousands of agent Spaces do it) and the LLM API domains are not on the abuse
  blocklist.

**Risk assessment for PocketAgent (BYOK → OpenAI/Anthropic):**
- **Today: works.** `api.openai.com` and `api.anthropic.com` are on 443 and not DNS-blocked.
- **Latent risk: medium.** The blocking policy is explicitly expanding ("cracking down"). If HF ever
  adds LLM-API domains to the blocklist (e.g., to push users to HF Inference Providers), the agent
  breaks with no code change. **Mitigation:** keep an LLM-API proxy option (a tiny Cloudflare
  Worker / Vercel function that forwards to OpenAI) so the Space calls a domain HF hasn't blocked.

---

## 6. Cold start time

- **Sleeping Space (woke by request):** ~**1 minute** for the first request to respond (Medium
  FastAPI guide, Oct 2025: "The first request may take up to 1 minute to respond.").
- **Paused/deep-cold Space:** ~**2 minutes** before the app server even starts booting (forum #72154:
  "it consistently takes ~2 minutes for a paused Space to start booting").
- `/tmp` caches are wiped on wake — any model cache must be rebuilt or baked into the image.

**For an interactive phone agent,** a 1-minute cold start after 48 h idle is acceptable (the phone
shows a "waking runtime…" state). To avoid it entirely, run a free external pinger (GitHub Actions
cron or an uptime monitor) hitting `GET /` every ~30 min to keep the Space warm — the same trick
PocketAgent already uses for Codespaces, just with a longer natural idle window.

---

## 7. Long-term stability of the free tier (2025–2026)

- **Free CPU Spaces tier: stable.** Still $0, no CC, 2 vCPU/16 GB/50 GB. Multiple 2026 pricing
  guides (metacto, eesel, hackceleration, techjacksolutions) all confirm "Free Hub $0/mo … basic
  CPU Spaces." No indication the free CPU tier is being deprecated (unlike Fly.io's free tier,
  killed in 2024, which Codespaces' architecture doc already flags).
- **Tightening signals to watch:**
  - **Outbound-request crackdown** (§5) — the biggest moving part. HF is actively restricting
    egress to "abuse-prone" services. Could widen to LLM APIs.
  - **Pro billing surprises** — Reddit reports of $300 overage bills on Pro with no spend cap
    (forum/r/huggingface). Doesn't affect the free tier directly but signals HF is monetizing harder.
  - **ZeroGPU quota tweaks** (3.5 min/day free) — irrelevant to a CPU-only agent runtime.

Net: the *free CPU compute* looks durable; the *network egress policy* is the fragile part.

---

## Side-by-side: HF Spaces vs Codespaces (current PocketAgent choice)

| Need | HF Spaces (free) | GitHub Codespaces (free) | Winner |
|---|---|---|---|
| Free, no CC | ✅ | ✅ (120 core-hrs/mo) | Tie |
| Full Linux + apt/pip | ⚠️ apt only at **build** time (UID 1000, no runtime sudo) | ✅ full sudo at runtime | **Codespaces** |
| Persistent storage | ❌ ephemeral 50 GB (paid bucket for persistence) | ✅ 15 GB survives stops | **Codespaces** |
| Public HTTPS URL, no browser | ✅ `*.hf.space`, immediate | ✅ `*.app.github.dev` | Tie (HF simpler) |
| Idle lifetime before sleep | ✅ **48 h** | ⚠️ 30 min default (tunable) | **HF Spaces** |
| Cold start | ~1 min (sleeping) | ~10–30 s | **Codespaces** |
| WebSocket on FastAPI `/agent` | ⚠️ proxy 404 bug to verify | ✅ works | **Codespaces** |
| Outbound to LLM APIs | ⚠️ works today, blocking policy expanding | ✅ unrestricted | **Codespaces** |
| Quota ceiling | ❌ none (always free) | ⚠️ 120 core-hrs/mo | **HF Spaces** |
| API control from phone | ✅ HF Hub API + git push | ✅ `gh` CLI + REST | Tie |

---

## Recommendation for PocketAgent

1. **Keep Codespaces as the primary backend.** Its full-sudo Linux, persistent 15 GB, unrestricted
   egress, and clean WebSocket support map directly onto the existing runtime with zero changes.
2. **Add an HF Docker Space as an optional second backend** the phone can select (Settings screen
   already supports a base URL + secret). This gives users without GitHub a path, and provides
   failover if Codespaces quota runs out.
3. **If adopting HF Spaces, make these portability changes** (good practice regardless of host):
   - **State:** persist `Session.messages` and `.pocketagent/todos.json` to an HF Dataset repo
     (free) keyed by `session_id`; the phone's `resume_session_id` handshake already supports resume.
   - **WS path:** test `WS /agent` on HF; if it 404s at the proxy, either move WS to `/` or add a
     one-line Nginx reverse proxy in the Dockerfile, or ship an SSE fallback on `GET /agent/stream`.
   - **LLM egress:** keep a pluggable `llm_proxy_url` config so an OpenAI/Anthropic call can be
     routed through a Cloudflare Worker if HF ever blocks the direct domain.
   - **Keep-warm:** add a GitHub Actions cron (or uptime-monitor) pinging `GET /` every 30 min to
     stay under the 48 h sleep threshold and avoid the 1-min cold start.
   - **Dockerfile:** bake all `apt-get` deps (ripgrep, etc.) into the image; the agent's `Bash`
     tool will run as UID 1000 with no sudo.

**Bottom line:** HF Spaces meets every hard requirement (free Linux, browserless public HTTPS,
48 h sandbox lifetime, LLM-API egress today) but trades away runtime sudo, persistent disk, and
WebSocket reliability versus Codespaces. Use it as a resilient secondary host, not a replacement.
