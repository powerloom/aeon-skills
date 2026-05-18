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
mkdir -p .bds-cache

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
    mkdir -p memory
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

# BDS base URL
BDS_BASE_URL="${BDS_BASE_URL:-https://bds.powerloom.io/api}"

# Fetch latest all-trades snapshot (covers all pools)
echo "Fetching latest trades snapshot from BDS..."
EPOCH_PARAM=""
if [ -f ".bds-cache/last_epoch.txt" ]; then
    LAST_EPOCH=$(cat .bds-cache/last_epoch.txt)
    EPOCH_PARAM="?from_epoch=$((LAST_EPOCH + 1))"
    echo "Resuming from epoch $((LAST_EPOCH + 1))"
fi

# Use curl to fetch the snapshot
# Response includes X-BDS-Credit-Balance header
curl -s -D .bds-cache/headers.txt \
    -H "Authorization: Bearer $BDS_API_KEY" \
    -H "Accept: application/json" \
    "${BDS_BASE_URL}/mpp/snapshot/allTrades/latest${EPOCH_PARAM}" \
    -o .bds-cache/latest.json 2>&1 || true

# Check response
if [ ! -s .bds-cache/latest.json ]; then
    echo "ERROR: Empty response from BDS API"
    exit 1
fi

# Check for errors in response
if grep -q '"error"' .bds-cache/latest.json 2>/dev/null; then
    echo "ERROR: BDS API returned error:"
    cat .bds-cache/latest.json
    exit 1
fi

# Extract epoch from response for next run
EPOCH=$(python3 -c "
import json
with open('.bds-cache/latest.json') as f:
    data = json.load(f)
    if 'epoch' in data:
        print(data['epoch'])
    elif 'verification' in data and 'epoch' in data.get('verification', {}):
        print(data['verification']['epoch'])
    else:
        print('unknown')
" 2>/dev/null || echo "unknown")

if [ "$EPOCH" != "unknown" ]; then
    echo "$EPOCH" > .bds-cache/last_epoch.txt
    echo "Cached epoch: $EPOCH"
fi

# Log credit balance if available
if [ -f ".bds-cache/headers.txt" ]; then
    CREDITS=$(grep -i "X-BDS-Credit-Balance" .bds-cache/headers.txt | awk '{print $2}' | tr -d '\r\n')
    if [ -n "$CREDITS" ]; then
        echo "BDS Credit Balance: $CREDITS"
    fi
fi

# For pulse mode, also fetch time series data
if [ "$MODE" = "pulse" ]; then
    echo "Fetching time series data for pulse analysis..."
    curl -s -H "Authorization: Bearer $BDS_API_KEY" \
        "${BDS_BASE_URL}/mpp/timeSeries/ethPrice?window=1h" \
        -o .bds-cache/timeseries.json 2>/dev/null || true
fi

# For defi-analyst mode, fetch additional context
if [ "$MODE" = "defi-analyst" ]; then
    echo "Fetching additional context for DeFi analysis..."
    curl -s -H "Authorization: Bearer $BDS_API_KEY" \
        "${BDS_BASE_URL}/mpp/dailyActiveTokens" \
        -o .bds-cache/active-tokens.json 2>/dev/null || true
    curl -s -H "Authorization: Bearer $BDS_API_KEY" \
        "${BDS_BASE_URL}/mpp/dailyActivePools" \
        -o .bds-cache/active-pools.json 2>/dev/null || true
fi

echo "=== Pre-fetch complete ==="
echo "Cached data in .bds-cache/"
ls -la .bds-cache/

exit 0
