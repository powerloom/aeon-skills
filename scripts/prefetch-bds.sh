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

# Use bds-agent to fetch latest all-trades snapshot
# bds-agent handles the API endpoint correctly
echo "Fetching latest trades snapshot using bds-agent..."

export BDS_BASE_URL="${BDS_BASE_URL:-https://bds.powerloom.io/api}"

# Fetch using bds-agent client - it knows the correct endpoints
# NOTE: fetch() is async, must use asyncio.run()
python3 << 'PYTHON'
import os
import json
import asyncio
from bds_agent.client import fetch

async def main():
    base_url = os.environ.get("BDS_BASE_URL", "https://bds.powerloom.io/api")
    api_key = os.environ.get("BDS_API_KEY")
    
    try:
        # Fetch latest allTrades snapshot (no epoch = latest)
        # fetch() is async, must await it
        result = await fetch(
            base_url,
            "/mpp/snapshot/allTrades",
            api_key
        )
        
        # Write to cache
        with open(".bds-cache/latest.json", "w") as f:
            json.dump(result.data, f, indent=2)
        
        # Log credit balance if available
        if result.credit_balance:
            print(f"BDS Credit Balance: {result.credit_balance}")
        
        # Extract epoch for tracking
        if hasattr(result, 'data') and isinstance(result.data, dict):
            epoch = result.data.get('epoch') or result.data.get('verification', {}).get('epoch')
            if epoch:
                with open(".bds-cache/last_epoch.txt", "w") as f:
                    f.write(str(epoch))
                print(f"Cached epoch: {epoch}")
        
        print("Successfully cached BDS data")
        
    except Exception as e:
        print(f"ERROR: Failed to fetch BDS data: {e}")
        # Write error to cache so skill knows what happened
        with open(".bds-cache/latest.json", "w") as f:
            json.dump({"error": str(e)}, f)
        exit(1)

asyncio.run(main())
PYTHON

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
