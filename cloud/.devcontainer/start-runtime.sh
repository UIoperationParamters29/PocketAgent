#!/usr/bin/env bash
# PocketAgent runtime auto-start with public tunnel.
#
# Problem: GitHub Codespaces' public port URL only works AFTER the codespace
# is opened in a browser (which registers the port forward). This makes it
# impossible to connect from the phone app without first opening the codespace.
#
# Solution: Use a tunneling service (serveo.net — free, no account, no install)
# that exposes port 8000 on a public URL the runtime controls. The phone app
# connects to that URL instead of the codespace's port-forward URL.
#
# If serveo is down, fall back to the codespace port forward (requires browser open).
set -uo pipefail

cd /workspaces/PocketAgent/cloud/runtime 2>/dev/null || exit 1

# Install deps if needed
if ! python -c "import fastapi" 2>/dev/null; then
  pip install -e . -q 2>&1 | tail -3
fi

# Kill existing uvicorn + ssh tunnel
pkill -f "python.*-m.*uvicorn.*app.main" 2>/dev/null || true
pkill -f "ssh.*-R.*80:localhost:8000.*serveo" 2>/dev/null || true
sleep 1

# Resolve channel secret
SECRET_FILE="$HOME/.pocketagent-secret"
if [ -z "${PA_CHANNEL_SECRET:-}" ]; then
  if [ -f "$SECRET_FILE" ]; then
    export PA_CHANNEL_SECRET="$(cat "$SECRET_FILE")"
  else
    EPHEM=$(openssl rand -hex 16)
    echo "$EPHEM" > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
    export PA_CHANNEL_SECRET="$EPHEM"
    echo "[PocketAgent] Channel secret: $EPHEM"
  fi
fi

# Start uvicorn
setsid nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/pocketagent.log 2>&1 < /dev/null &
UVICORN_PID=$!
disown $UVICORN_PID 2>/dev/null || true
echo "[PocketAgent] uvicorn started: PID $UVICORN_PID"
sleep 3

# Verify uvicorn is up locally
if curl -sS http://localhost:8000/ > /tmp/health.json 2>&1; then
  echo "[PocketAgent] ✅ Local health check passed"
else
  echo "[PocketAgent] ⚠️  Local health check failed:"
  tail -15 /tmp/pocketagent.log 2>&1
fi

# ---- Establish a public tunnel via serveo.net ----
# serveo creates a random subdomain like https://abc123.serveo.net that forwards to localhost:8000
# This is free, no account, no install — just SSH with a remote-forward flag.
TUNNEL_LOG=/tmp/serveo.log
echo "[PocketAgent] Establishing public tunnel via serveo.net..."

# Try serveo first (most reliable free option)
# -o StrictHostKeyChecking=no to auto-accept serveo's host key
# -R 80:localhost:8000 = remote-forward serveo's port 80 to our port 8000
# serveo responds with the public URL on stdout
setsid nohup ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
  -R 80:localhost:8000 serveo.net > "$TUNNEL_LOG" 2>&1 < /dev/null &
TUNNEL_PID=$!
disown $TUNNEL_PID 2>/dev/null || true

# Wait for serveo to print the URL
TUNNEL_URL=""
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 2
  TUNNEL_URL=$(grep -oE 'https://[a-z0-9]+\.serveo\.net' "$TUNNEL_LOG" 2>/dev/null | head -1)
  if [ -n "$TUNNEL_URL" ]; then
    break
  fi
done

if [ -n "$TUNNEL_URL" ]; then
  echo "[PocketAgent] ✅ Public tunnel: $TUNNEL_URL"
  # Write the tunnel URL to a well-known file the phone app can fetch via GitHub API
  # (via the runtime-status branch)
  echo "{\"tunnel_url\": \"$TUNNEL_URL\", \"codespace\": \"${CODESPACE_NAME:-unknown}\", \"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > /workspaces/PocketAgent/TUNNEL_URL.json
  cd /workspaces/PocketAgent
  git config user.email "pocketagent-runtime@codespace" 2>/dev/null
  git config user.name "PocketAgent Runtime" 2>/dev/null
  git checkout -B runtime-status 2>/dev/null || git checkout runtime-status 2>/dev/null
  git add TUNNEL_URL.json 2>/dev/null
  git commit -m "Tunnel URL update" --no-verify 2>/dev/null
  # Use the GITHUB_TOKEN that Codespaces auto-provides
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    git push "https://x-access-token:${GITHUB_TOKEN}@github.com/UIoperationParamters29/PocketAgent.git" runtime-status --force 2>/dev/null && echo "[PocketAgent] Tunnel URL pushed to runtime-status branch"
  else
    git push origin runtime-status --force 2>/dev/null && echo "[PocketAgent] Tunnel URL pushed"
  fi
  git checkout main 2>/dev/null || true
else
  echo "[PocketAgent] ⚠️  Tunnel failed. Log:"
  cat "$TUNNEL_LOG" 2>&1 | tail -10
  echo "[PocketAgent] Falling back to codespace port forward: https://${CODESPACE_NAME:-codespace}-8000.app.github.dev"
  echo "[PocketAgent] (This requires the codespace to be opened in a browser first.)"
fi

echo ""
echo "=== PocketAgent runtime ready ==="
echo "  Local: http://localhost:8000"
echo "  Tunnel: ${TUNNEL_URL:-<none — using codespace port forward>}"
echo "  Channel secret: ${PA_CHANNEL_SECRET:0:8}..."
