---
name: Powerloom BDS
description: Verified on-chain data from Powerloom BDS — whale alerts, token flow, pulse signals, DeFi analysis
schedule: "*/5 * * * *"
tags: [crypto, defi, data]
permissions:
  - contents:write
---

> **${var}** — Mode to run: `whale-radar` (default) | `token-flow` | `pulse` | `defi-analyst`. If empty, defaults to `whale-radar`.

## Goal

Fetch verified blockchain data from Powerloom BDS and dispatch actionable alerts. Every alert carries an on-chain verification CID — the data is consensus-finalized, not trust-the-vendor.

## Pre-conditions

The pre-fetch script (`scripts/prefetch-bds.sh`) has already:
1. Read `lastStreamEpoch` from state file
2. Fetched trades from `from_epoch = lastStreamEpoch + 1` (or latest if no cursor)
3. Cached results in `.bds-cache/latest.json`

This skill reads the cached JSON — no network calls needed inside the sandbox.

## State Management

This skill maintains **epoch cursor** and **deduplication state** in `memory/powerloom-bds-state.json`:

```json
{
  "lastStreamEpoch": 25121752,
  "lastEmittedBlock": 25121752,
  "emittedFingerprints": ["0xabc...:25121750", "0xdef...:25121751"],
  "last_run": "2026-05-18T12:00:00Z",
  "alerts_sent": 3,
  "mode": "whale-radar"
}
```

- **lastStreamEpoch**: Next run fetches from this epoch + 1
- **emittedFingerprints**: LRU-500 list of `txHash:blockNumber` to prevent duplicate alerts
- **lastEmittedBlock**: Track highest block seen

## Config

Read from `memory/powerloom-bds.yml`:

```yaml
mode: whale-radar

thresholds:
  whale_usd: 10000     # Minimum USD for whale alert

pulse:
  window_minutes: 5
  cooldown_minutes: 10

analyst:
  report_cadence: hourly
  include_verification_probe: true
```

## Steps

### 1. Load state

Read `memory/powerloom-bds-state.json`. If missing, initialize:

```json
{
  "lastStreamEpoch": null,
  "lastEmittedBlock": 0,
  "emittedFingerprints": []
}
```

### 2. Read cached BDS data

Read `.bds-cache/latest.json`. If missing/error, log `POWERLOOM_BDS_CACHE_MISS` and end.

Extract:
- `epoch.begin`, `epoch.end` — epoch range
- `verification.cid`, `verification.epochId` — proof
- Trade array from `data` or root level

### 3. Process trades (whale-radar mode)

1. **Flatten trades** from snapshot:
   - Look for `data.trades[]` or `trades[]` or flat trade list
   - Each trade has: `poolAddress`, `data`, `log.transactionHash`, `log.blockNumber`

2. **For each trade**:
   - Calculate USD value: `|calculated_token0_amount| * token0_price` or use `usd_amount` if present
   - Skip if USD < `thresholds.whale_usd`
   - Build fingerprint: `f"{txHash}:{blockNumber}"`
   - Skip if fingerprint in `emittedFingerprints` (already alerted)
   - Add fingerprint to `emittedFingerprints` (keep max 500, LRU)

3. **Format alert**:
   ```
   🐳 Whale alert: {token_in} → {token_out}  ${amount}

   Pool: {pool_address}
   Epoch: {epoch_id}
   Tx: {tx_hash}
   ✅ Verified on-chain
      cid: {cid}
      project: {project_id}
   ```

4. **Dispatch** via `./notify`

### 4. Update state

After processing all trades:

```json
{
  "lastStreamEpoch": <epoch.end from fetched data>,
  "lastEmittedBlock": <max blockNumber seen>,
  "emittedFingerprints": <updated list, max 500>,
  "last_run": "<ISO timestamp>",
  "alerts_sent": <count>,
  "mode": "whale-radar"
}
```

Write to `memory/powerloom-bds-state.json`.

### 5. Log

Append to `memory/logs/${today}.md`:

```markdown
### powerloom-bds
- Epoch: {epoch_range}
- Trades scanned: {count}
- Whale alerts: {count}
- Status: OK
```

## Deduplication Logic

```python
def fingerprint_trade(trade):
    tx = trade.get("log", {}).get("transactionHash") or trade.get("transactionHash", "")
    bn = trade.get("log", {}).get("blockNumber") or trade.get("blockNumber", 0)
    return f"{tx}:{bn}"

def was_emitted(state, fp):
    return fp in state.get("emittedFingerprints", [])

def remember_fingerprint(state, fp, max_size=500):
    fps = state.get("emittedFingerprints", [])
    fps.append(fp)
    while len(fps) > max_size:
        fps.pop(0)
    state["emittedFingerprints"] = fps
```

## Verification

Every alert includes on-chain proof. Verify independently:

```bash
cast call 0xa1100CB00Acd3cA83a7C8F4DAA42701D1Eaf4A6c \
  "maxSnapshotsCid(address,string,uint256)(string,uint8)" \
  0x4198Bf81B55EE4Af6f9Ddc176F8021960813f641 \
  "<project_id>" \
  <epoch_int> \
  --rpc-url https://rpc-v2.powerloom.network
```

## Error handling

| Condition | Action |
|-----------|--------|
| No config | Log `POWERLOOM_BDS_NO_CONFIG`, end silently |
| Cache missing | Log `POWERLOOM_BDS_CACHE_MISS`, end silently |
| Same epoch as lastStreamEpoch | Log `POWERLOOM_BDS_STALE`, end silently |
| No trades above threshold | Log `POWERLOOM_BDS_OK` with epoch, end silently |
| All trades already emitted | Log `POWERLOOM_BDS_OK` (caught up), end silently |

## Resources

- `references/bds-api.md` — BDS endpoint catalog
- `references/verification.md` — How to verify CIDs on-chain
- https://docs.powerloom.io/agents-and-bds/quickstart
