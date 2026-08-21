#!/usr/bin/env bash
# Pack local exemplars into a zip for EXEMPLARS_URL (not committed).
#
# Usage (from repo root):
#   ./scripts/pack-exemplars.sh /tmp/mtg-exemplars.zip
#
# Upload that zip somewhere private and set EXEMPLARS_URL on the Render mtg-api service.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
src="$root/backend/assets/exemplars"
out="${1:?usage: $0 /path/to/mtg-exemplars.zip}"

if [[ ! -d "$src" ]]; then
  echo "missing $src — run prepare_exemplars first" >&2
  exit 1
fi

# Zip contents are archetype folders at the top level (portal/, tangle/, …).
(cd "$src" && zip -r "$out" portal tangle banner panel mural -x '*.bak*' -x '*bak-pre*/*')
echo "wrote $out"
unzip -l "$out" | head -40
