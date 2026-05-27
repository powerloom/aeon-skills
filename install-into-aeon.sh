#!/usr/bin/env bash
# Install powerloom-bds skill + companion scripts into an Aeon fork.
#
# Prerequisite: clone https://github.com/powerloom/aeon-skills (this repo).
#
# Usage — pick ONE:
#   cd /path/to/your-aeon-fork && /path/to/aeon-skills/install-into-aeon.sh
#   /path/to/aeon-skills/install-into-aeon.sh /path/to/your-aeon-fork
#
# With no argument, AEON_ROOT defaults to $(pwd) — you must already be in the fork.
#
# What it copies:
#   powerloom-bds/  -> skills/powerloom-bds/
#   scripts/*       -> scripts/   (prefetch, fetch, normalize, process, postprocess)
#
# Also runs patch-aeon-fork.sh (.gitignore, workflow BDS_API_KEY, state commit allowlist).
# Full operator guide: INSTALL.md

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

for script in prefetch-bds.sh fetch-bds-epochs.py bds_normalize.py bds_rate_limit.py process-bds-skill.py postprocess-bds.sh; do
  cp "$SKILL_REPO/scripts/$script" "$AEON_ROOT/scripts/$script"
  chmod +x "$AEON_ROOT/scripts/$script" 2>/dev/null || true
done

echo "Done."
echo "  skills/powerloom-bds/SKILL.md"
echo "  scripts/prefetch-bds.sh"
echo "  scripts/bds_rate_limit.py"
echo "  scripts/fetch-bds-epochs.py"
echo "  scripts/bds_normalize.py"
echo "  scripts/process-bds-skill.py"
echo "  scripts/postprocess-bds.sh"
echo ""

bash "$SKILL_REPO/patch-aeon-fork.sh" "$AEON_ROOT"

echo ""
echo "Next (see INSTALL.md):"
echo "  1. Enable powerloom-bds in aeon.yml (if not already)"
echo "  2. GitHub secret BDS_API_KEY=sk_live_..."
echo "  3. Notify channel secrets (TELEGRAM_* / DISCORD_* / SLACK_*)"
echo "  4. git commit && push"
