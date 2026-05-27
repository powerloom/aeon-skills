# powerloom-bds on Aeon — architecture

**Canonical skill repo:** [powerloom/aeon-skills](https://github.com/powerloom/aeon-skills)

OpenClaw reference (same product, different runtime): [powerloom/powerloom-bds-univ3](https://github.com/powerloom/powerloom-bds-univ3) — `scripts/whale-cron.mjs`.

---

## Why this exists

Aeon runs skills inside a **sandboxed** GitHub Actions job. The LLM cannot reliably:

- Hold an epoch cursor across runs
- Deduplicate alerts by tx fingerprint
- Call paid BDS APIs with secrets during sandbox execution

So **whale-radar on Aeon splits work** the same way OpenClaw splits cron vs MCP:

| Phase | Where it runs | What it does |
|-------|----------------|--------------|
| Prefetch | Before sandbox (`prefetch-bds.sh`) | Fetch BDS, process trades, advance cursor |
| Skill | Sandbox (`SKILL.md`) | Read `.bds-cache/alerts.json`, call `./notify` |
| Postprocess | After sandbox (`postprocess-bds.sh`) | Backup cursor if needed |

The agent **dispatches** pre-built alerts. It does **not** re-fetch or rewrite state.

---

## Data path (whale-radar)

```
memory/powerloom-bds-state.json     lastStreamEpoch cursor (committed to git)
           │
           ▼
scripts/fetch-bds-epochs.py         GET /mpp/snapshot/allTrades/{block} loop
           │                         from lastStreamEpoch+1 → tip (max 100/run)
           ▼
.bds-cache/stream-events.json       array of normalized snapshots
           │
           ▼
scripts/process-bds-skill.py        walk tradeData, dedupe, format alerts
           │
           ├──► .bds-cache/alerts.json
           ├──► memory/powerloom-bds-state.json (updated cursor)
           └──► .pending-notify/bds-alerts.txt (optional)
           │
           ▼
SKILL.md (Claude)                   ./notify per alert string
           │
           ▼
aeon.yml post-run                   deliver .pending-notify/ to Telegram
```

---

## API choice (important)

**Use:** `GET /mpp/snapshot/allTrades/{block_number}` — one Ethereum block (epoch) per request.

**Do not use** query params on bare `/mpp/snapshot/allTrades` — `from_epoch` and `max_events` are **ignored** by the server.

**Do not use** SSE (`/mpp/stream/allTrades`) for this cron skill — different JSON shape, flat session pricing, unnecessary for 5–15 min polling. SSE is for long-lived firehose agents.

See [09-streaming-session.md](https://github.com/powerloom/ai-coord-docs/blob/main/bds-mpp-integration/09-streaming-session.md) — metered per-epoch snapshot is the recommended path.

---

## Scripts

| File | Role |
|------|------|
| `prefetch-bds.sh` | Wipe `.bds-cache/`, set env, run fetch + processor |
| `fetch-bds-epochs.py` | Per-block snapshot loop + pool metadata cache |
| `bds_normalize.py` | Unwrap snapshot vs legacy SSE-shaped payloads |
| `process-bds-skill.py` | Whale threshold, dedupe, OpenClaw-style alert text |
| `postprocess-bds.sh` | Advance cursor from `epoch_range.txt` if processor skipped |

---

## Config

`memory/powerloom-bds.yml`:

```yaml
mode: whale-radar

thresholds:
  whale_usd: 1000
```

Inline `#` comments on the same line are supported (processor strips them).

---

## Ephemeral vs committed state

| Path | Committed? |
|------|------------|
| `memory/powerloom-bds-state.json` | Yes — epoch cursor + fingerprints |
| `memory/powerloom-bds.yml` | Yes — operator config |
| `.bds-cache/` | **No** — regenerated every prefetch; add to `.gitignore` |

---

## Scheduler (Aeon fork)

`messages.yml` tick → `gh workflow run aeon.yml -f skill=powerloom-bds` (not nested workflow_call).

Dedup window for `*/5` schedule ≈ 15 min between dispatches. Expect **batch catch-up** (many epochs per run) not one block per Telegram ping.

---

## Verified reference run (2026-05-27)

Prefetch:

```
Cursor lastStreamEpoch=25185635 → fetch from block 25185636
Fetched 5 snapshot(s): 25185636 - 25185640
process-bds-skill: epochs=5 trades=82 alerts=27 cursor=25185640
```

27 Telegram alerts delivered via `.pending-notify/` post-run path.

---

## What makes BDS whale alerts different

1. **Block-accurate USD** — `calculated_trade_amount_usd` from BDS compute at that epoch, not a live aggregator quote.
2. **On-chain verification** — each snapshot can carry `verification.cid` + `epochId` tied to Powerloom consensus.
3. **No LLM in the hot path** — threshold, dedupe, and cursor are deterministic Python.
4. **True catch-up** — missed blocks are scanned sequentially; alerts are not sampled only at chain tip.
5. **Human-readable dispatch** — pool symbols, BUY/SELL, Etherscan links; Telegram-safe (no raw `projectId` with underscores).
