#!/bin/bash
# Pre-fetch BDS data before the skill runs
# This script runs with full env access (including BDS_API_KEY from GitHub secrets)
# before the Claude sandbox starts.

set -e

echo "=== Powerloom BDS Pre-fetch ==="
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ -z "$BDS_API_KEY" ]; then
    echo "ERROR: BDS_API_KEY not set"
    echo "Add BDS_API_KEY to your GitHub repository secrets"
    exit 1
fi

# Ephemeral cache — do not commit .bds-cache/ (see .gitignore)
mkdir -p memory
rm -rf .bds-cache
mkdir -p .bds-cache

if ! command -v bds-agent &> /dev/null; then
    echo "Installing bds-agent from PyPI..."
    pip install bds-agent
fi

CONFIG_FILE="memory/powerloom-bds.yml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "WARN: No config file at $CONFIG_FILE — creating default"
    cat > "$CONFIG_FILE" << 'EOF'
mode: whale-radar

thresholds:
  whale_usd: 25000

pulse:
  window_minutes: 5
  cooldown_minutes: 10

analyst:
  report_cadence: hourly
  include_verification_probe: true
EOF
fi

MODE=$(grep -E '^mode:' "$CONFIG_FILE" | awk '{print $2}' || echo "whale-radar")
echo "Mode: $MODE"

STATE_FILE="memory/powerloom-bds-state.json"
export BDS_BASE_URL="${BDS_BASE_URL:-https://bds.powerloom.io/api}"
export BDS_MAX_EPOCHS_PER_RUN="${BDS_MAX_EPOCHS_PER_RUN:-50}"
export BDS_RATE_LIMIT_RPM="${BDS_RATE_LIMIT_RPM:-200}"
export BDS_POOL_METADATA_CONCURRENCY="${BDS_POOL_METADATA_CONCURRENCY:-2}"
export FROM_EPOCH=""

if [ -f "$STATE_FILE" ]; then
    LAST_EPOCH=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('lastStreamEpoch', '') or '')" 2>/dev/null || echo "")
    if [ -n "$LAST_EPOCH" ] && [ "$LAST_EPOCH" != "null" ] && [ "$LAST_EPOCH" != "None" ]; then
        export FROM_EPOCH=$((LAST_EPOCH + 1))
        echo "Cursor lastStreamEpoch=$LAST_EPOCH → fetch from block $FROM_EPOCH"
    fi
fi

if [ -z "$FROM_EPOCH" ]; then
    echo "No cursor — will fetch latest finalized epoch only"
fi

python3 scripts/fetch-bds-epochs.py
python3 scripts/process-bds-skill.py

echo "=== Pre-fetch complete ==="
ls -la .bds-cache/

exit 0
