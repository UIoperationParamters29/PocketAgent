#!/usr/bin/env bash
# PocketAgent codespace bootstrap — runs once on codespace creation.
# Mirrors the z.ai agentic sandbox: Python 3.12, Node 24, ripgrep, common tools.
# Also installs the runtime + starts it (so the public port-8000 URL works
# immediately after codespace creation).
set -euo pipefail

echo "=== PocketAgent bootstrap ==="

# 1. System packages (z.ai parity: ripgrep, ffmpeg, fonts for charts, etc.)
sudo apt-get update -qq
sudo apt-get install -y -qq \
  ripgrep \
  ffmpeg \
  poppler-utils \
  fonts-noto-cjk fonts-noto-color-emoji \
  git curl wget unzip jq \
  build-essential \
  > /dev/null

# 2. Python runtime deps
cd /workspaces/PocketAgent/cloud/runtime
python -m pip install --upgrade pip -q
pip install -e . -q
echo "Runtime installed."
python -c "import app.main; print('runtime module loads OK')"

# 3. Workspace dirs (mirror z.ai layout)
mkdir -p ~/workspace/{download,scripts,upload,skills,.pocketagent}

# 4. Default AGENTS.md if missing
if [ ! -f ~/workspace/AGENTS.md ]; then
  cat > ~/workspace/AGENTS.md <<'EOF'
# AGENTS.md — custom instructions for your PocketAgent

This file is read at the start of every session. Use it to teach the agent
your preferences, coding style, common tools, etc.

## Examples
- "Always use TypeScript."
- "When writing Python, prefer uv for envs."
- "My timezone is Asia/Baghdad."
EOF
  echo "Wrote default AGENTS.md to ~/workspace/AGENTS.md"
fi

# 5. Start the runtime in the background (so port 8000 is alive immediately)
# If PA_CHANNEL_SECRET is set (via Codespaces secret), use it. Otherwise ephemeral.
if [ -z "${PA_CHANNEL_SECRET:-}" ]; then
  EPHEM=$(openssl rand -hex 16)
  export PA_CHANNEL_SECRET="$EPHEM"
  echo ""
  echo "==============================================================="
  echo "  PocketAgent runtime starting with EPHEMERAL channel secret:"
  echo "    $EPHEM"
  echo "  (For production, set PA_CHANNEL_SECRET as a Codespaces secret"
  echo "   at github.com/settings/codespaces — scoped to this repo.)"
  echo "==============================================================="
fi

# Kill any stale uvicorn (but not this script itself — match on python -m uvicorn)
pkill -f "python.*-m.*uvicorn.*app.main" 2>/dev/null || true
sleep 1
cd /workspaces/PocketAgent/cloud/runtime
# Start uvicorn detached so it survives the postCreateCommand shell exiting
setsid nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/pocketagent.log 2>&1 < /dev/null &
UVICORN_PID=$!
disown $UVICORN_PID 2>/dev/null || true
echo "PocketAgent runtime started: PID $UVICORN_PID"
sleep 5
if curl -sS http://localhost:8000/ > /dev/null 2>&1; then
  echo "  ✅ Health check passed"
else
  echo "  ⚠️  Health check failed — /tmp/pocketagent.log:"
  tail -25 /tmp/pocketagent.log 2>&1
fi

# 6. Helpful message
cat <<EOF

=== PocketAgent ready ===
Workspace:  ~/workspace  (your agent's "own computer")
Runtime:    running on port 8000
Endpoint:   https://${CODESPACE_NAME:-codespace}-8000.app.github.dev
Channel:    set PA_CHANNEL_SECRET in your phone app's onboarding
EOF

# 7. Write a status file to the workspace (so external debugging works).
# This file is committed on bootstrap, providing an "I'm alive" signal.
STATUS_FILE=/workspaces/PocketAgent/.codespace-status.md
cat > "$STATUS_FILE" <<EOF
# Codespace Status

Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Codespace: ${CODESPACE_NAME:-unknown}
Channel secret set: $([ -n "${PA_CHANNEL_SECRET:-}" ] && echo yes || echo no)

## Runtime
- Local health check: $(curl -sS http://localhost:8000/ > /dev/null 2>&1 && echo OK || echo FAILED)
- Port 8000 forward URL: https://${CODESPACE_NAME:-codespace}-8000.app.github.dev

## Bootstrap log
\`\`\`
$(tail -30 /tmp/pocketagent.log 2>&1)
\`\`\`
EOF
echo "Status file written: $STATUS_FILE"
