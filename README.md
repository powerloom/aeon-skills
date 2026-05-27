# powerloom-aeon-skill

Canonical **skill package** for [Aeon](https://github.com/aaronjmars/aeon). Published as **`powerloom/aeon-skills`** on GitHub.

**Do not edit the fork copy (`anomit-aeon/skills/powerloom-bds`) as source of truth.** Change this repo, then re-install into your Aeon fork.

## What makes this good

Whale Radar on Aeon is not “an LLM that polls Uniswap.” It is:

1. **Verified block data** — trades and USD amounts from BDS epoch snapshots; alerts include on-chain verification (CID, epoch) when present.
2. **Deterministic catch-up** — `fetch-bds-epochs.py` walks `GET /mpp/snapshot/allTrades/{block}` from cursor+1 to chain tip (up to **50** snapshots/run). No tip-only sampling, no ignored `from_epoch` query hacks.
3. **OpenClaw parity, headless runtime** — same whale logic as `powerloom-bds-univ3/scripts/whale-cron.mjs`, but split for GitHub Actions: prefetch owns fetch + cursor; Claude only dispatches `./notify`.
4. **Rich, Telegram-safe alerts** — pool metadata (USDC/WETH), BUY/SELL, Etherscan links; project slug only in verification footer.
5. **Cheap agent step** — skill reads pre-built `.bds-cache/alerts.json`; no sandbox network, no LLM rewriting `powerloom-bds-state.json`.

Deep dive: [powerloom-bds/references/architecture.md](powerloom-bds/references/architecture.md)

## Repo layout

```
powerloom-aeon-skill/
├── powerloom-bds/              # Skill tree (SKILL.md + references)
├── scripts/
│   ├── prefetch-bds.sh         # Orchestrator (wipes .bds-cache/, runs fetch + process)
│   ├── fetch-bds-epochs.py     # Per-block snapshot loop (recommended BDS API)
│   ├── bds_normalize.py          # Snapshot shape helpers
│   ├── process-bds-skill.py      # Whale threshold, dedupe, alert formatting, cursor
│   └── postprocess-bds.sh        # Cursor backup after skill run
├── templates/powerloom-bds.yml.example
├── install-into-aeon.sh
└── README.md
```

## What stays in the Aeon fork

| Path | Owner |
|------|--------|
| `aeon.yml` | Enable schedule |
| `memory/powerloom-bds-state.json` | Runtime cursor (committed by Actions) |
| `memory/powerloom-bds.yml` | Operator threshold / mode |
| `.bds-cache/` | **Ephemeral** — must be in `.gitignore` |
| GitHub secret `BDS_API_KEY` | Your fork |

## Install

**Full guide:** [INSTALL.md](INSTALL.md) (blog-ready, any Aeon fork)

```bash
git clone https://github.com/powerloom/aeon-skills.git
cd /path/to/your-aeon-fork
/path/to/aeon-skills/install-into-aeon.sh
```

With no argument the script uses `$(pwd)` — **cd into your fork first**, or pass the fork path explicitly. Both are valid.

Copies skill + five scripts; runs `patch-aeon-fork.sh` for `.gitignore`, workflow `BDS_API_KEY`, and cursor auto-commit.

## How it runs

```
messages.yml (cron) → aeon.yml skill=powerloom-bds
  → prefetch-bds.sh
      → fetch-bds-epochs.py   # snapshot/{block} loop
      → process-bds-skill.py  # alerts.json + state update
  → Claude reads SKILL.md → ./notify each alert
  → postprocess-bds.sh (backup cursor)
  → commit memory/powerloom-bds-state.json
```

## Quick start

1. Fork Aeon, run `install-into-aeon.sh`
2. Secret `BDS_API_KEY` from https://bds-metering.powerloom.io/metering
3. Optional: `cp templates/powerloom-bds.yml.example memory/powerloom-bds.yml`
4. Enable in `aeon.yml` (e.g. `*/5 * * * *` — effective dispatch ~15 min due to scheduler dedup)
5. Add `.bds-cache/` to `.gitignore`; remove from git if previously committed
6. Push

## Modes

| Mode | Status |
|------|--------|
| **whale-radar** | Shipped |
| token-flow | OpenClaw `token-flow.mjs` until ported |
| pulse | OpenClaw / `bds-agent trade` until ported |
| defi-analyst | Not in prefetch yet |

## Reference run (2026-05-27)

5 epochs, 82 trades scanned, **27 whale alerts** dispatched — see operator notes in workspace `daily_notes_work_plan/2026-05-27/successful-run.md`.

## Related

- [architecture.md](powerloom-bds/references/architecture.md)
- [bds-api.md](powerloom-bds/references/bds-api.md)
- [ai-coord-docs AEON_WHALE_RADAR](https://github.com/powerloom/ai-coord-docs/blob/main/recipes/AEON_WHALE_RADAR.md) (recipe spec)
- [OpenClaw skill](https://github.com/powerloom/powerloom-bds-univ3)
- [bds-agent CLI](https://github.com/powerloom/bds-agent-py)
- [Powerloom Docs](https://docs.powerloom.io/agents-and-bds/quickstart)

## License

MIT
