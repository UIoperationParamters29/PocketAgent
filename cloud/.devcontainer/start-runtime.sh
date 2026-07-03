#!/usr/bin/env bash
# PocketAgent runtime auto-start — runs on EVERY codespace start (postStartCommand).
# Idempotent: kills any existing uvicorn, then starts fresh.
#
# Also writes a status file to a git branch so external monitoring (the phone app
# or our CI) can verify the runtime is alive without needing to SSH in.
set -uo pipefail

cd /workspaces/PocketAgent/cloud/runtime 2>/dev/null || {
  echo "[PocketAgent] ERROR: /workspaces/PocketAgent/cloud/runtime not found"
  exit 1
}

# Make sure deps are installed (idempotent — bootstrap.sh already ran on create)
if ! python -c "import fastapi" 2>/dev/null; then
  echo "[PocketAgent] Installing runtime deps..."
  pip install -e . -q 2>&1 | tail -3
fi

# Kill any existing uvicorn on port 8000
pkill -f "python.*-m.*uvicorn.*app.main" 2>/dev/null || true
sleep 1

# Resolve the channel secret
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
  fi
fi

# Start uvicorn detached
setsid nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/pocketagent.log 2>&1 < /dev/null &
UVICORN_PID=$!
disown $UVICORN_PID 2>/dev/null || true
echo "[PocketAgent] Runtime started: PID $UVICORN_PID"

# Wait for it to come up
sleep 4

# Health check + write status
HEALTH_OK="no"
HEALTH_RESP=""
if curl -sS http://localhost:8000/ > /tmp/health.json 2>&1; then
  HEALTH_OK="yes"
  HEALTH_RESP=$(cat /tmp/health.json)
fi

# Write a status file to a special branch (runtime-status) so external tools
# can verify the runtime is alive via the GitHub API.
STATUS_FILE=/tmp/runtime-status.json
cat > "$STATUS_FILE" <<EOF
{
  "codespace": "${CODESPACE_NAME:-unknown}",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "uvicorn_pid": $UVICORN_PID,
  "health_ok": $HEALTH_OK,
  "channel_secret_set": $([ -n "${PA_CHANNEL_SECRET:-}" ] && echo true || echo false),
  "channel_secret_prefix": "${PA_CHANNEL_SECRET:0:8}",
  "port": 8000,
  "runtime_url": "https://${CODESPACE_NAME:-codespace}-8000.app.github.dev",
  "health_response": $(python3 -c "import json; print(json.dumps(open('/tmp/health.json').read() if __import__('os').path.exists('/tmp/health.json') else ''))" 2>/dev/null || echo '""'),
  "log_tail": $(python3 -c "import json,os; p='/tmp/pocketagent.log'; print(json.dumps(open(p).read()[-1000:] if os.path.exists(p) else ''))" 2>/dev/null || echo '""')
}
EOF

# Commit the status file to a runtime-status branch (so the phone app can fetch it)
cd /workspaces/PocketAgent
git config user.email "pocketagent-runtime@codespace"
git config user.name "PocketAgent Runtime"
git checkout -B runtime-status 2>/dev/null || git checkout runtime-status 2>/dev/null
cp "$STATUS_FILE" /workspaces/PocketAgent/RUNTIME_STATUS.json
git add RUNTIME_STATUS.json 2>/dev/null
git commit -m "Runtime status update ($(date -u +%H:%M:%S))" --no-verify 2>/dev/null
git push origin runtime-status --force 2>/dev/null && echo "[PocketAgent] Status pushed to runtime-status branch" || echo "[PocketAgent] Could not push status (no token?)"

# Switch back to main for normal use
git checkout main 2>/dev/null || true

# Final log
if [ "$HEALTH_OK" = "yes" ]; then
  echo "[PocketAgent] ✅ Runtime is healthy at https://${CODESPACE_NAME:-codespace}-8000.app.github.dev"
  echo "  Channel secret: ${PA_CHANNEL_SECRET:0:8}..."
else
  echo "[PocketAgent] ⚠️  Health check failed. Log:"
  tail -20 /tmp/pocketagent.log 2>&1
fi
