#!/usr/bin/env bash
# PocketAgent codespace bootstrap — runs once on codespace creation.
# Mirrors the z.ai agentic sandbox: Python 3.12, Node 24, ripgrep, common tools.
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

# 5. Helpful message
cat <<'EOF'

=== PocketAgent ready ===
Workspace:  ~/workspace  (your agent's "own computer")
Runtime:    cd cloud/runtime && uvicorn app.main:app --reload
Endpoint:   http://localhost:8000  (publicly: https://<codespace>-8000.app.github.dev)

Set your channel secret:
  export PA_CHANNEL_SECRET="<any-strong-secret>"
EOF
