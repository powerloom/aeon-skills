#!/usr/bin/env bash
# Install powerloom-bds skill + companion scripts into an Aeon fork.
#
# Usage (from your Aeon repo root):
#   /path/to/powerloom-aeon-skill/install-into-aeon.sh
#   /path/to/powerloom-aeon-skill/install-into-aeon.sh /path/to/anomit-aeon
#
# What it copies:
#   powerloom-bds/  -> skills/powerloom-bds/
#   scripts/*       -> scripts/   (prefetch, process, postprocess)

set -euo pipefail

SKILL_REPO="$(cd "$(dirname "$0")" && pwd)"
AEON_ROOT="${1:-$(pwd)}"

if [[ ! -f "$AEON_ROOT/aeon.yml" ]]; then
  echo "ERROR: $AEON_ROOT does not look like an Aeon repo (missing aeon.yml)" >&2
  exit 1
fi

echo "Installing powerloom-bds from $SKILL_REPO into $AEON_ROOT"

mkdir -p "$AEON_ROOT/skills" "$AEON_ROOT/scripts"
rm -rf "$AEON_ROOT/skills/powerloom-bds"
cp -r "$SKILL_REPO/powerloom-bds" "$AEON_ROOT/skills/powerloom-bds"

for script in prefetch-bds.sh process-bds-skill.py postprocess-bds.sh; do
  cp "$SKILL_REPO/scripts/$script" "$AEON_ROOT/scripts/$script"
  chmod +x "$AEON_ROOT/scripts/$script" 2>/dev/null || true
done

echo "Done."
echo "  skills/powerloom-bds/SKILL.md"
echo "  scripts/prefetch-bds.sh"
echo "  scripts/process-bds-skill.py"
echo "  scripts/postprocess-bds.sh"
echo ""
echo "Next: set BDS_API_KEY secret, enable powerloom-bds in aeon.yml, push."
