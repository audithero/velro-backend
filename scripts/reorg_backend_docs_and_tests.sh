#!/bin/zsh
set -euo pipefail

ROOT="/Users/apostle_mbp/Dropbox/0xAPOSTLE/00.WINDSURF/Claudecurrent/velro-003/velro-backend"

ARCH="$ROOT/docs/archive/legacy-local-reports"
mkdir -p "$ARCH" "$ROOT/tests/migrated" "$ROOT/scripts/testing"

# 1) Archive loose backend-level markdown reports that live at backend root
find "$ROOT" -maxdepth 1 -type f -name "*.md" \
  ! -name "README.md" \
  ! -name "BACKEND_MASTER_HISTORY_AND_DECISIONS.md" \
  -exec mv -v {} "$ARCH"/ \;

# 2) Move stray test scripts/sh into structured places
mv -v "$ROOT"/hotfix_*.sh "$ROOT/scripts" 2>/dev/null || true
mv -v "$ROOT"/*test*.sh "$ROOT/scripts/testing" 2>/dev/null || true

# 3) Prefer pytest-style tests under tests/
if [ -d "$ROOT/testing" ]; then
  find "$ROOT/testing" -type f -name "*.py" -exec mv -v {} "$ROOT/tests/migrated"/ \;
fi

echo "Backend reorg complete."


