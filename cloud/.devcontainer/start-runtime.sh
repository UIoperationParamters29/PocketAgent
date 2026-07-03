#!/usr/bin/env bash
# PocketAgent runtime auto-start with public tunnel.
#
# Problem: GitHub Codespaces' public port URL only works AFTER the codespace
# is opened in a browser AND the editor registers the port forward.
#
# Solution: Use serveo.net (free, no account) to establish a public tunnel.
# The tunnel URL is published via the GitHub REST API to the 'runtime-status'
# branch so the phone app can fetch it.
set -uo pipefail

cd /workspaces/PocketAgent/cloud/runtime 2>/dev/null || exit 1

# Install deps if needed
if ! python -c "import fastapi" 2>/dev/null; then
  pip install -e . -q 2>&1 | tail -3
fi

# Kill existing processes
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
sleep 4

# Local health check
if curl -sS http://localhost:8000/ > /tmp/health.json 2>&1; then
  echo "[PocketAgent] ✅ Local health check passed"
else
  echo "[PocketAgent] ⚠️ Local health check failed:"
  tail -15 /tmp/pocketagent.log 2>&1
fi

# ---- Establish serveo.net tunnel ----
TUNNEL_LOG=/tmp/serveo.log
echo "[PocketAgent] Establishing public tunnel via serveo.net..."

setsid nohup ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
  -R 80:localhost:8000 serveo.net > "$TUNNEL_LOG" 2>&1 < /dev/null &
TUNNEL_PID=$!
disown $TUNNEL_PID 2>/dev/null || true

# Wait for serveo to print the URL (up to 20s)
TUNNEL_URL=""
for i in $(seq 1 10); do
  sleep 2
  TUNNEL_URL=$(grep -oE 'https://[a-z0-9]+\.serveo\.net' "$TUNNEL_LOG" 2>/dev/null | head -1)
  if [ -n "$TUNNEL_URL" ]; then
    break
  fi
done

# Build status JSON
STATUS_JSON=$(python3 -c "
import json, os
health = ''
try:
    with open('/tmp/health.json') as f:
        health = f.read()[:200]
except: pass
log = ''
try:
    with open('/tmp/pocketagent.log') as f:
        log = f.read()[-500:]
except: pass
print(json.dumps({
    'tunnel_url': os.environ.get('TUNNEL_URL', ''),
    'codespace': os.environ.get('CODESPACE_NAME', 'unknown'),
    'ts': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
    'uvicorn_pid': os.environ.get('UVICORN_PID', ''),
    'health': health,
    'log_tail': log,
}))
")

echo "[PocketAgent] Status JSON: $STATUS_JSON"

# ---- Publish tunnel URL via GitHub REST API ----
# Use GITHUB_TOKEN (auto-provided by Codespaces) to update TUNNEL_URL.json
# on the runtime-status branch. This is more reliable than git push.
publish_url() {
  local token="$1"
  local content_b64="$2"
  
  # Try to get existing file SHA (needed for updates, not creates)
  local sha=""
  sha=$(curl -sS -H "Authorization: token $token" \
    "https://api.github.com/repos/UIoperationParamters29/PocketAgent/contents/TUNNEL_URL.json?ref=runtime-status" \
    2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('sha',''))" 2>/dev/null)
  
  # Build request body
  local body
  if [ -n "$sha" ]; then
    body=$(python3 -c "
import json
print(json.dumps({
    'message': 'Update tunnel URL',
    'content': '$content_b64',
    'branch': 'runtime-status',
    'sha': '$sha',
}))
")
  else
    body=$(python3 -c "
import json
print(json.dumps({
    'message': 'Create tunnel URL',
    'content': '$content_b64',
    'branch': 'runtime-status',
}))
")
  fi
  
  # Create or update the file
  curl -sS -X PUT \
    -H "Authorization: token $token" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/UIoperationParamters29/PocketAgent/contents/TUNNEL_URL.json" \
    -d "$body" > /tmp/github-api-response.json 2>&1
  
  if python3 -c "import json; d=json.load(open('/tmp/github-api-response.json')); assert 'content' in d" 2>/dev/null; then
    echo "[PocketAgent] ✅ Tunnel URL published to runtime-status branch"
    return 0
  else
    echo "[PocketAgent] ⚠️ GitHub API response:"
    cat /tmp/github-api-response.json 2>&1 | head -5
    return 1
  fi
}

CONTENT_B64=$(echo "$STATUS_JSON" | base64 -w0)

# Try GITHUB_TOKEN first (auto-provided by Codespaces)
if [ -n "${GITHUB_TOKEN:-}" ]; then
  echo "[PocketAgent] Publishing via GITHUB_TOKEN..."
  publish_url "$GITHUB_TOKEN" "$CONTENT_B64" || true
else
  echo "[PocketAgent] GITHUB_TOKEN not set, trying gh CLI..."
  # Try gh CLI (pre-authenticated in Codespaces)
  if command -v gh > /dev/null 2>&1; then
    GH_TOKEN_VAL=$(gh auth token 2>/dev/null)
    if [ -n "$GH_TOKEN_VAL" ]; then
      publish_url "$GH_TOKEN_VAL" "$CONTENT_B64" || true
    else
      echo "[PocketAgent] ⚠️ gh not authenticated"
    fi
  else
    echo "[PocketAgent] ⚠️ No GITHUB_TOKEN and no gh CLI"
  fi
fi

# Final status
if [ -n "$TUNNEL_URL" ]; then
  echo ""
  echo "=== PocketAgent runtime ready ==="
  echo "  Tunnel: $TUNNEL_URL"
  echo "  Local: http://localhost:8000"
  echo "  Channel secret: ${PA_CHANNEL_SECRET:0:8}..."
else
  echo ""
  echo "=== PocketAgent runtime ready (fallback) ==="
  echo "  ⚠️ Tunnel failed — using codespace port forward"
  echo "  Port: https://${CODESPACE_NAME:-codespace}-8000.app.github.dev"
  echo "  Local: http://localhost:8000"
  echo "  Channel secret: ${PA_CHANNEL_SECRET:0:8}..."
  echo ""
  echo "  Serveo log:"
  cat "$TUNNEL_LOG" 2>&1 | tail -10
fi
