#!/usr/bin/env bash
set -euo pipefail

MP="main.py"
STAMP=".router_hotfix_applied"

if [[ ! -f "$STAMP" ]]; then
  echo "No hotfix stamp found. Nothing to rollback."; exit 0
fi

# Un-comment lines we commented (remove only the leading "# HOTFIX: ")
# Keep user comments intact.
tmpfile="$(mktemp)"
sed 's/^# HOTFIX: //' "$MP" > "$tmpfile" && mv "$tmpfile" "$MP"

# (Optional) Remove the inline endpoint block
# Comment out instead of deleting (safer)
if grep -q '=== HOTFIX: Inline models endpoint' "$MP"; then
  awk '
    BEGIN{skip=0}
    /=== HOTFIX: Inline models endpoint/ { skip=1; print "# HOTFIX: BEGIN inline models endpoint disabled"; next }
    /=== \/HOTFIX ===/ { skip=0; print "# HOTFIX: END inline models endpoint disabled"; next }
    { if (skip) { print "# HOTFIX: " $0 } else { print $0 } }
  ' "$MP" > "$tmpfile" && mv "$tmpfile" "$MP"
fi

rm -f "$STAMP"
echo "Routers re-enabled (lines uncommented). Redeploy/restart to take effect."