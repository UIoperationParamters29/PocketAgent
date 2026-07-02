#!/usr/bin/env bash
# Auto-start the PocketAgent runtime when the codespace starts.
# Runs uvicorn in the background; logs to /tmp/pocketagent.log.
# If PA_CHANNEL_SECRET isn't set, generates an ephemeral one and prints it once.
set -uo pipefail

# Generate an ephemeral channel secret if not provided by Codespaces secrets
if [ -z "${PA_CHANNEL_SECRET:-}" ]; then
  EPHEM=$(openssl rand -hex 16)
  export PA_CHANNEL_SECRET="$EPHEM"
  echo ""
  echo "==============================================================="
  echo "  PocketAgent runtime starting with EPHEMERAL channel secret:"
  echo "    $EPHEM"
  echo "  (For production, set PA_CHANNEL_SECRET as a Codespaces secret)"
  echo "==============================================================="
  echo ""
fi

# Make sure deps are installed (idempotent — bootstrap.sh already ran)
cd /workspaces/PocketAgent/cloud/runtime 2>/dev/null || exit 0
if ! python -c "import fastapi" 2>/dev/null; then
  pip install -e . -q
fi

# Kill any existing uvicorn on port 8000
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1

# Start uvicorn in the background
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/pocketagent.log 2>&1 &
echo "PocketAgent runtime started: PID $!"
echo "  Port 8000 (public): https://${CODESPACE_NAME:-codespace}-8000.app.github.dev"
echo "  Logs: /tmp/pocketagent.log"
echo "  Channel secret: ${PA_CHANNEL_SECRET:0:8}... (set as PA_CHANNEL_SECRET in your phone app)"

# Wait briefly and verify
sleep 3
if curl -sS http://localhost:8000/ > /dev/null 2>&1; then
  echo "  ✅ Health check passed"
else
  echo "  ⚠️  Health check failed — see /tmp/pocketagent.log"
  tail -10 /tmp/pocketagent.log 2>&1
fi
