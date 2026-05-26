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

Dispatch actionable alerts from **pre-processed** BDS data. Prefetch + `scripts/process-bds-skill.py` already advanced the epoch cursor and deduplicated trades (OpenClaw parity). This skill **must not** re-fetch or rewrite cursor state unless processing failed.

Every alert carries on-chain verification when present in the cached snapshot.

## Pre-conditions

`scripts/prefetch-bds.sh` has already:

1. Read `lastStreamEpoch` from `memory/powerloom-bds-state.json`
2. Fetched `/mpp/snapshot/allTrades` from `lastStreamEpoch + 1` (or latest)
3. Run `scripts/process-bds-skill.py` → updated state + `.bds-cache/alerts.json`

This skill reads the cached JSON — no network calls needed inside the sandbox.

## Steps

### 1. Read alerts cache

Read `.bds-cache/alerts.json`. Structure:

```json
{
  "alerts": ["🐳 Whale alert: ...", "..."],
  "epoch_end": 25149997
}
```

If missing or `alerts` is empty:

- Append to `memory/logs/${today}.md`: `powerloom-bds — no alerts`
- End silently with log code `POWERLOOM_BDS_OK`

### 2. Dispatch alerts

For each string in `alerts[]`, run:

```bash
./notify "<alert text>"
```

Do **not** duplicate alerts — the processor already deduped fingerprints.

### 3. Log

Append to `memory/logs/${today}.md`:

```markdown
### powerloom-bds
- Epoch end: {epoch_end}
- Alerts sent: {count}
- Status: OK
```

## State (do not rewrite)

`memory/powerloom-bds-state.json` is maintained by **`scripts/process-bds-skill.py`** in prefetch. Do not decrement `lastStreamEpoch` or clear `emittedFingerprints`.

## Error handling

| Condition | Action |
|-----------|--------|
| No config | Log `POWERLOOM_BDS_NO_CONFIG`, end silently |
| Cache/alerts missing | Log `POWERLOOM_BDS_CACHE_MISS`, end silently |
| Empty alerts | Log `POWERLOOM_BDS_OK`, end silently |

## Non-whale modes

`token-flow`, `pulse`, and `defi-analyst` are **not** deterministic in prefetch yet. For those modes, log `POWERLOOM_BDS_MODE_SKIP` and end — use OpenClaw scripts locally until ported.

## Resources

- `references/bds-api.md` — BDS endpoint catalog
- `references/verification.md` — How to verify CIDs on-chain
- https://docs.powerloom.io/agents-and-bds/quickstart
