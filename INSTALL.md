# Install powerloom-bds on any Aeon fork

Canonical skill repo: [github.com/powerloom/aeon-skills](https://github.com/powerloom/aeon-skills)

This guide is for operators forking [Aeon](https://github.com/aaronjmars/aeon) who want **verified Uniswap V3 whale alerts** on a schedule (Telegram / Discord / Slack via Aeon `./notify`).

---

## What you get

- Per-block BDS snapshot catch-up (`GET /mpp/snapshot/allTrades/{block}`)
- Deterministic cursor in `memory/powerloom-bds-state.json` (auto-committed)
- LLM only dispatches pre-built alerts — no sandbox fetch, no cursor hallucination
- OpenClaw `whale-cron.mjs` parity, adapted for GitHub Actions

---

## Prerequisites

1. Fork [Aeon](https://github.com/aaronjmars/aeon) and clone it locally
2. Aeon base setup done (Anthropic or other model secret, at least one notify channel)
3. BDS API key (`sk_live_...`) from [bds-metering.powerloom.io/metering](https://bds-metering.powerloom.io/metering) (2 free credits)

---

## Step 1 — Clone aeon-skills and install files

```bash
git clone https://github.com/powerloom/aeon-skills.git
cd your-aeon-fork   # must contain aeon.yml at repo root

/path/to/aeon-skills/install-into-aeon.sh
# or, from any directory:
/path/to/aeon-skills/install-into-aeon.sh /path/to/your-aeon-fork
```

**Usage note:** The script defaults to `$(pwd)` when no argument is given — so **cd into your Aeon fork first**, or pass the fork path explicitly. Both forms are correct.

This copies:

| Source | Destination |
|--------|-------------|
| `powerloom-bds/` | `skills/powerloom-bds/` |
| 5 scripts | `scripts/prefetch-bds.sh`, `fetch-bds-epochs.py`, `bds_normalize.py`, `process-bds-skill.py`, `postprocess-bds.sh` |

It also runs `patch-aeon-fork.sh` (`.gitignore`, workflow env, commit allowlist).

---

## Step 2 — Enable the skill in `aeon.yml`

If `install-into-aeon.sh` printed a snippet, add it under `skills:`:

```yaml
  powerloom-bds: { enabled: true, schedule: "*/5 * * * *" }
```

Cron in `aeon.yml` is `*/5`; effective dispatch is often ~15 min due to Aeon scheduler dedup — normal.

---

## Step 3 — GitHub secrets

In your fork: **Settings → Secrets and variables → Actions**

| Secret | Required | Notes |
|--------|----------|-------|
| `BDS_API_KEY` | **Yes** | `sk_live_...` from BDS metering |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | For TG | Or Discord / Slack webhook secrets per [Aeon docs](https://github.com/aaronjmars/aeon) |

Vanilla Aeon does **not** pass `BDS_API_KEY` into prefetch automatically. `patch-aeon-fork.sh` adds it to the **Run pre-fetch scripts** env block. If you skipped patching, add manually:

```yaml
          BDS_API_KEY: ${{ secrets.BDS_API_KEY }}
```

under the prefetch step in `.github/workflows/aeon.yml`.

---

## Step 4 — Optional config

```bash
cp templates/powerloom-bds.yml.example memory/powerloom-bds.yml
```

Edit `thresholds.whale_usd` (e.g. `1000` for more alerts, `25000` for fewer). If the file is missing, prefetch creates a default at `whale_usd: 25000`.

---

## Step 5 — Commit and push

```bash
git add skills/powerloom-bds scripts/prefetch-bds.sh scripts/fetch-bds-epochs.py \
        scripts/bds_normalize.py scripts/process-bds-skill.py scripts/postprocess-bds.sh \
        .gitignore aeon.yml
# include .github/workflows/aeon.yml if patch-aeon-fork changed it
git commit -m "Add powerloom-bds whale radar skill"
git push
```

Ensure `.bds-cache/` is **not** tracked (ephemeral; wiped each run).

---

## Step 6 — Verify first run

Actions → **aeon** workflow → run `powerloom-bds` (or wait for cron).

Healthy prefetch log:

```
Cursor lastStreamEpoch=… → fetch from block …
Fetched N snapshot(s): A - B
process-bds-skill: epochs=N trades=T alerts=A cursor=B
```

First run with no cursor fetches **latest finalized epoch only**. Subsequent runs catch up block-by-block (max 100/run).

Silent skill runs (`no alerts`) are normal when no swap exceeds your threshold.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Prefetch: `BDS_API_KEY not set` | Add secret; ensure workflow prefetch env maps `BDS_API_KEY: ${{ secrets.BDS_API_KEY }}` |
| `Fetched N snapshots` but `trades=0` always | Wrong API path — must be `/mpp/snapshot/allTrades/{block}`, not `?from_epoch=` |
| Cursor never advances | Add `memory/powerloom-bds-state.json` to workflow auto-commit allowlist (patch script does this) |
| Telegram formatting broken | Use shipped alert template (project slug only in verification footer) |
| Alerts years apart | Tip-only sampling bug — reinstall scripts from aeon-skills |

---

## Re-sync after aeon-skills updates

```bash
cd your-aeon-fork
/path/to/aeon-skills/install-into-aeon.sh
git diff   # review, commit, push
```

---

## Related

- [README.md](README.md) — architecture summary
- [powerloom-bds/references/architecture.md](powerloom-bds/references/architecture.md) — data path deep dive
- [AEON_WHALE_RADAR recipe](https://github.com/powerloom/ai-coord-docs/blob/main/recipes/AEON_WHALE_RADAR.md)
- [OpenClaw whale-cron reference](https://github.com/powerloom/powerloom-bds-univ3/blob/main/scripts/whale-cron.mjs)
