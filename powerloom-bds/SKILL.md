---
name: Powerloom BDS
description: Verified on-chain data from Powerloom BDS — whale alerts, token flow, pulse signals, DeFi analysis
schedule: "*/15 * * * *"
tags: [crypto, defi, data]
permissions:
  - contents:write
---

> **${var}** — Mode to run: `whale-radar` (default) | `token-flow` | `pulse` | `defi-analyst`. If empty, defaults to `whale-radar`.

## Goal

Fetch verified blockchain data from Powerloom BDS and dispatch actionable alerts. Every alert carries an on-chain verification CID — the data is consensus-finalized, not trust-the-vendor.

## Pre-conditions

The pre-fetch script (`scripts/prefetch-bds.sh`) has already:
1. Installed `bds-agent` from PyPI
2. Called BDS API with `BDS_API_KEY` from GitHub secrets
3. Cached results in `.bds-cache/latest.json`

This skill reads the cached JSON — no network calls needed inside the sandbox.

## Config

This skill reads configuration from `memory/powerloom-bds.yml`. If the file doesn't exist, create it from the template:

```yaml
# memory/powerloom-bds.yml
mode: whale-radar  # whale-radar | token-flow | pulse | defi-analyst

pools:
  - address: "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
    name: "USDC/WETH 0.05%"
  - address: "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8"
    name: "USDC/WETH 0.3%"

thresholds:
  whale_usd: 25000        # Minimum USD for whale alert
  volume_spike_mult: 2.5  # Volume burst multiplier
  price_move_pct: 0.4     # Price movement percentage
  flow_imbalance_pct: 35  # Flow imbalance percentage

# Pulse-specific (only used when mode: pulse)
pulse:
  window_minutes: 5
  cooldown_minutes: 10

# DeFi Analyst specific (only used when mode: defi-analyst)
analyst:
  report_cadence: hourly  # hourly | daily
  include_verification_probe: true
```

## Steps

### 1. Read configuration

Read `memory/powerloom-bds.yml` to get:
- `mode` — which analysis to run
- `pools` — which pools to watch
- `thresholds` — alert thresholds

If the file doesn't exist, log `POWERLOOM_BDS_NO_CONFIG` and end.

### 2. Read cached BDS data

Read `.bds-cache/latest.json` (created by pre-fetch script). The cache contains:
- Latest epoch's snapshot data
- Verification CID and epoch ID
- Timestamp

If the cache is empty or missing, log `POWERLOOM_BDS_CACHE_MISS` and end.

### 3. Run mode-specific analysis

#### Mode: whale-radar (default)

For each pool in `pools`:
1. Filter trades from cached snapshot where `usd_amount >= thresholds.whale_usd`
2. For each whale trade:
   - Extract: pool, token pair, amount, direction (buy/sell), tx hash
   - Extract: `verification.cid`, `verification.epoch`
3. Format alert:
   ```
   🐳 Whale alert: {token_in} → {token_out}  ${amount}
   
   Pool: {pool_address}
   Epoch: {epoch_id}
   Tx: {tx_hash}
   ✅ Verified on-chain
      cid: {cid}
      project: {project_id}
   ```

#### Mode: token-flow

For a specific token (configured in `var` or memory file):
1. Aggregate all trades across watched pools for that token
2. Calculate net flow (buys vs sells)
3. Detect flow imbalance > `thresholds.flow_imbalance_pct`
4. Format multi-pool summary with verification

#### Mode: pulse

1. Analyze cached data for confluence of signals:
   - Price move ≥ `thresholds.price_move_pct`
   - Volume burst ≥ `thresholds.volume_spike_mult`
   - Flow imbalance ≥ `thresholds.flow_imbalance_pct`
2. All three within `pulse.window_minutes` = PULSE_FIRE
3. Cooldown: `pulse.cooldown_minutes` between fires
4. Format: `⚡ PULSE: {direction} {token} — {reasons}`

#### Mode: defi-analyst

1. Generate narrated market summary from cached data
2. Include random verification probe (1 in 5 reports)
3. Format as structured DeFi brief

### 4. Dispatch alerts

For each formatted alert:
1. Send via `./notify`
2. Log to memory/logs/${today}.md under `### powerloom-bds`

### 5. Update state

Update `memory/powerloom-bds-state.json`:
```json
{
  "last_epoch": 24785842,
  "last_run": "2026-05-18T12:00:00Z",
  "alerts_sent": 3,
  "mode": "whale-radar"
}
```

This enables:
- Detection of stale data (same epoch as last run)
- Cooldown tracking for pulse mode
- Run metrics for skill-health

## Verification

Every alert includes a verification block. Users can verify independently:

```bash
cast call 0xa1100CB00Acd3cA83a7C8F4DAA42701D1Eaf4A6c \
  "maxSnapshotsCid(address,string,uint256)(string,uint8)" \
  0x4198Bf81B55EE4Af6f9Ddc176F8021960813f641 \
  "<project_id>" \
  <epoch_int> \
  --rpc-url https://rpc-v2.powerloom.network
```

If the returned CID matches the alert, the data is consensus-verified.

## Output format

Keep notifications under 4000 chars. Lead with the signal, follow with verification.

Example (whale-radar):
```
🐳 Whale alert: WETH → USDC  $1,312,000

Pool: 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640
Epoch: 24785842
Tx: 0xa1b2...
✅ Verified on-chain
   cid: bafkrei...
   project: allTradesSnapshot:0x26c4...
```

## Error handling

| Condition | Action |
|-----------|--------|
| No config file | Log `POWERLOOM_BDS_NO_CONFIG`, end silently |
| Cache missing | Log `POWERLOOM_BDS_CACHE_MISS`, end silently |
| Same epoch as last run | Log `POWERLOOM_BDS_STALE`, skip (no new data) |
| API error in pre-fetch | Pre-fetch logs error, cache is empty, this skill ends |
| No matches for thresholds | Log `POWERLOOM_BDS_OK` with epoch, end silently |

## Sandbox note

The sandbox blocks outbound network from Python/bash with env vars. The pre-fetch script (`scripts/prefetch-bds.sh`) runs **before** this skill with full env access. It:
- Reads `BDS_API_KEY` from GitHub secrets
- Calls BDS API via `bds-agent` or `curl`
- Writes to `.bds-cache/latest.json`

This skill only reads cached files — no network fallback needed.

## Dependencies

- **GitHub secret**: `BDS_API_KEY` — your `sk_live_...` key from https://bds-metering.powerloom.io/metering
- **Pre-fetch script**: `scripts/prefetch-bds.sh`
- **Config file**: `memory/powerloom-bds.yml`
- **Python package**: `bds-agent` (installed by pre-fetch)

## Resources

- `references/bds-api.md` — BDS endpoint catalog
- `references/verification.md` — How to verify CIDs on-chain
- https://docs.powerloom.io/agents-and-bds/quickstart — Getting started
- https://pypi.org/project/bds-agent/ — bds-agent package
