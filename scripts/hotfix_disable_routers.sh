#!/usr/bin/env bash
set -euo pipefail

MP="main.py"
STAMP=".router_hotfix_applied"

if [[ -f "$STAMP" ]]; then
  echo "Hotfix already applied. (Found $STAMP)"; exit 0
fi

# 1) Backup once
cp -n "$MP" "${MP}.bak.$(date +%Y%m%d%H%M%S)"

# 2) Comment out router imports + include_router lines for models/projects/diagnostics
#    (idempotent; only comments active lines)
tmpfile="$(mktemp)"
awk '
  # Helper to prefix with "# HOTFIX:" only if not already commented
  function cmt(line) { return (substr(line,1,1)=="#" ? line : "# HOTFIX: " line) }

  {
    line=$0
    # Comment imports
    if ($0 ~ /^from[[:space:]]+routers\.(models|projects|diagnostics)[[:space:]]+import[[:space:]]+router[[:space:]]+as[[:space:]]+/) {
      print cmt(line); next
    }
    # Comment include_router registrations
    if ($0 ~ /app\.include_router\(.+prefix="\/api\/v1\/(models|projects)("|\/|,)/) {
      print cmt(line); next
    }
    # diagnostics router (with or without prefix)
    if ($0 ~ /app\.include_router\(.+diagnostics/) {
      print cmt(line); next
    }
    print line
  }
' "$MP" > "$tmpfile" && mv "$tmpfile" "$MP"

# 3) Ensure Optional is imported (if not already)
grep -q 'from typing import Optional' "$MP" || \
  sed -i '' '1s/^/from typing import Optional\n/' "$MP"

# 4) Inject minimal inline models endpoint if not present
if ! grep -q 'def get_supported_models_inline' "$MP"; then
  cat >> "$MP" <<'PYINLINE'

# === HOTFIX: Inline models endpoint (bypasses failing routers) ===
try:
    from fastapi import Query
except Exception:
    pass

@app.get("/api/v1/models/supported")
async def get_supported_models_inline(model_type: Optional[str] = Query(default=None)):
    """
    Minimal no-dep endpoint used while routers are disabled.
    Returns a static set so the UI can render.
    """
    data = {
        "source": "inline-hotfix",
        "timestamp": time.time(),
        "models": [
            {"id": "fal-ai/flux/schnell", "type": "image", "label": "FLUX Schnell"},
            {"id": "fal-ai/flux/dev",      "type": "image", "label": "FLUX Dev"},
            {"id": "fal-ai/stable-diffusion", "type": "image", "label": "Stable Diffusion"},
        ],
    }
    # Optional: filter by ?model_type=image
    if model_type:
        data["models"] = [m for m in data["models"] if m.get("type") == model_type]
    return data
# === /HOTFIX ===

PYINLINE
fi

touch "$STAMP"
echo "Router hotfix applied. Restart your app/process to load changes."