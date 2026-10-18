#!/usr/bin/env bash
# Install git pre-push hook for AI log submission (POSIX / Git Bash).
# Run once after cloning: bash scripts/setup_hooks.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
HOOK_FILE="$(git rev-parse --git-path hooks/pre-push)"

mkdir -p "$(dirname "$HOOK_FILE")"
sed 's/\r$//' "$SCRIPT_DIR/hooks/pre-push" > "$HOOK_FILE"

chmod +x "$HOOK_FILE"
chmod +x scripts/_pyrun.sh 2>/dev/null || true
echo "[ai-log] Git pre-push hook installed."

mkdir -p .ai-log
touch .ai-log/.gitkeep

echo "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
