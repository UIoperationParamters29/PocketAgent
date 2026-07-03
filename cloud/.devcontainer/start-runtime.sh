#!/usr/bin/env bash
# PocketAgent runtime auto-start — runs on EVERY codespace start (postStartCommand).
# Idempotent: kills any existing uvicorn, then starts fresh.
#
# The channel secret comes from:
#   1. PA_CHANNEL_SECRET env var (set via Codespaces secrets), OR
#   2. An ephemeral one generated + saved to ~/.pocketagent-secret (persists across restarts)
set -uo pipefail

cd /workspaces/PocketAgent/cloud/runtime 2>/dev/null || exit 0

# Make sure deps are installed (idempotent — bootstrap.sh already ran on create)
if ! python -c "import fastapi" 2>/dev/null; then
  pip install -e . -q 2>&1 | tail -3
fi

# Kill any existing uvicorn on port 8000
pkill -f "python.*-m.*uvicorn.*app.main" 2>/dev/null || true
sleep 1

# Resolve the channel secret:
# - If PA_CHANNEL_SECRET is set (via Codespaces secret), use it.
# - Otherwise, use the persisted ephemeral secret (or generate one if first run).
SECRET_FILE="$HOME/.pocketagent-secret"
if [ -z "${PA_CHANNEL_SECRET:-}" ]; then
  if [ -f "$SECRET_FILE" ]; then
    export PA_CHANNEL_SECRET="$(cat "$SECRET_FILE")"
  else
    EPHEM=$(openssl rand -hex 16)
    echo "$EPHEM" > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
    export PA_CHANNEL_SECRET="$EPHEM"
    echo "[PocketAgent] Generated persistent channel secret: $EPHEM"
    echo "  Set this same value in your phone app's Settings, OR"
    echo "  set PA_CHANNEL_SECRET as a Codespaces secret at github.com/settings/codespaces"
    echo "  (then stop + start the codespace for it to take effect)."
  fi
fi

# Start uvicorn detached (survives postStartCommand shell exit)
setsid nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/pocketagent.log 2>&1 < /dev/null &
UVICORN_PID=$!
disown $UVICORN_PID 2>/dev/null || true
echo "[PocketAgent] Runtime started: PID $UVICORN_PID"
echo "  Port 8000: https://${CODESPACE_NAME:-codespace}-8000.app.github.dev"
echo "  Secret: ${PA_CHANNEL_SECRET:0:8}... (full value above if ephemeral)"

# Brief health check
sleep 3
if curl -sS http://localhost:8000/ > /dev/null 2>&1; then
  echo "  ✅ Health check passed"
else
  echo "  ⚠️  Health check failed — log:"
  tail -10 /tmp/pocketagent.log 2>&1
fi
