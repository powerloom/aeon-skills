#!/bin/bash
# Pre-fetch BDS data before the skill runs
# This script runs with full env access (including BDS_API_KEY from GitHub secrets)
# before the Claude sandbox starts.

set -e

echo "=== Powerloom BDS Pre-fetch ==="
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Check for API key
if [ -z "$BDS_API_KEY" ]; then
    echo "ERROR: BDS_API_KEY not set"
    echo "Add BDS_API_KEY to your GitHub repository secrets"
    exit 1
fi

# Create cache directory
mkdir -p .bds-cache memory

# Install bds-agent if not present
if ! command -v bds-agent &> /dev/null; then
    echo "Installing bds-agent from PyPI..."
    pip install bds-agent
fi

# Read config to determine what to fetch
CONFIG_FILE="memory/powerloom-bds.yml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "WARN: No config file at $CONFIG_FILE"
    echo "Creating default config..."
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
    echo "Created default config at $CONFIG_FILE"
fi

# Extract mode from config
MODE=$(grep -E '^mode:' "$CONFIG_FILE" | awk '{print $2}' || echo "whale-radar")
echo "Mode: $MODE"

# Read last epoch from state file (for epoch cursor)
STATE_FILE="memory/powerloom-bds-state.json"
LAST_EPOCH=""
if [ -f "$STATE_FILE" ]; then
    LAST_EPOCH=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('lastStreamEpoch', '') or '')" 2>/dev/null || echo "")
fi

export BDS_BASE_URL="${BDS_BASE_URL:-https://bds.powerloom.io/api}"
export FROM_EPOCH=""

if [ -n "$LAST_EPOCH" ] && [ "$LAST_EPOCH" != "null" ] && [ "$LAST_EPOCH" != "None" ]; then
    echo "Resuming from epoch: $LAST_EPOCH"
    FROM_EPOCH=$((LAST_EPOCH + 1))
    export FROM_EPOCH
    echo "Fetching from epoch: $FROM_EPOCH"
else
    echo "No previous epoch found, fetching latest"
fi

# bds_agent.client.fetch is async — must use asyncio.run()
python3 << 'PYTHON'
import os
import json
import asyncio
from bds_agent.client import fetch

async def main():
    base_url = os.environ.get("BDS_BASE_URL", "https://bds.powerloom.io/api")
    api_key = os.environ.get("BDS_API_KEY")
    from_epoch_raw = os.environ.get("FROM_EPOCH", "").strip()

    params = {"max_events": 100}
    if from_epoch_raw:
        params["from_epoch"] = int(from_epoch_raw)

    result = await fetch(
        base_url,
        "/mpp/snapshot/allTrades",
        api_key,
        **params
    )

    with open(".bds-cache/latest.json", "w") as f:
        json.dump(result.data, f, indent=2)

    if result.credit_balance is not None:
        print(f"BDS Credit Balance: {result.credit_balance}")

    if isinstance(result.data, dict):
        epoch_data = result.data.get("epoch") or {}
        epoch_start = epoch_data.get("begin")
        epoch_end = epoch_data.get("end")
        if epoch_end is not None:
            with open(".bds-cache/epoch_range.txt", "w") as f:
                f.write(f"{epoch_start or 0}\n{epoch_end}\n")
            print(f"Epoch range: {epoch_start or '?'} - {epoch_end}")

    print("Successfully cached BDS data")

asyncio.run(main())
PYTHON

# Deterministic alert processing + epoch cursor (OpenClaw parity)
python3 scripts/process-bds-skill.py

echo "=== Pre-fetch complete ==="
echo "Cached data in .bds-cache/"
ls -la .bds-cache/

exit 0
