# Powerloom BDS — Aeon Skill

Canonical **skill package** for [Aeon](https://github.com/aaronjmars/aeon). Published as **`powerloom/aeon-skills`** on GitHub.

**Do not edit the fork copy (`anomit-aeon/skills/powerloom-bds`) as source of truth.** Change this repo, then re-install into your Aeon fork.

## Repo layout (what lives here)

```
powerloom-aeon-skill/
├── powerloom-bds/           # Skill tree (SKILL.md + references) — installed to skills/
├── scripts/
│   ├── prefetch-bds.sh      # Runs before Claude (network + secrets OK)
│   ├── process-bds-skill.py # Deterministic whale-radar + epoch cursor
│   └── postprocess-bds.sh   # Cursor backup after skill run
├── templates/
│   └── powerloom-bds.yml.example
├── install-into-aeon.sh     # Copy skill + scripts into an Aeon fork
└── README.md
```

## What stays in the Aeon fork (not this repo)

| Path | Owner |
|------|--------|
| `aeon.yml` | Your fork — enable/disable schedule |
| `memory/powerloom-bds-state.json` | Runtime state — committed by GH Actions |
| `memory/powerloom-bds.yml` | Your operator config |
| `.github/workflows/aeon.yml` | Upstream Aeon — optional fork patches only |
| GitHub secret `BDS_API_KEY` | Your fork |

## Install into an Aeon fork

### Option A — install script (recommended)

```bash
cd /path/to/your-aeon-fork
/path/to/powerloom-aeon-skill/install-into-aeon.sh
```

Copies **`powerloom-bds/` → `skills/powerloom-bds/`** and all **`scripts/*`** into the fork.

### Option B — add-skill + manual scripts

`./add-skill` only copies the skill directory — **not** the companion scripts.

```bash
./add-skill powerloom/aeon-skills powerloom-bds --force
cp /path/to/powerloom-aeon-skill/scripts/prefetch-bds.sh scripts/
cp /path/to/powerloom-aeon-skill/scripts/process-bds-skill.py scripts/
cp /path/to/powerloom-aeon-skill/scripts/postprocess-bds.sh scripts/
chmod +x scripts/prefetch-bds.sh scripts/postprocess-bds.sh
```

## How it runs (whale-radar)

1. **`scripts/prefetch-bds.sh`** (before sandbox): read `lastStreamEpoch`, fetch `allTrades` from epoch+1, run processor
2. **`scripts/process-bds-skill.py`**: dedupe, advance cursor, write `.bds-cache/alerts.json`
3. **Claude reads `SKILL.md`**: dispatch `./notify` for each pre-built alert (no LLM state logic)
4. **`scripts/postprocess-bds.sh`** (after sandbox): backup cursor from epoch cache

OpenClaw parity: deterministic scripts own cursor + dedupe; the agent only dispatches.

## Quick Start

### 1. Fork Aeon

```bash
git clone https://github.com/aaronjmars/aeon
cd aeon
```

### 2. Install this package

```bash
git clone https://github.com/powerloom/aeon-skills /tmp/aeon-skills
/tmp/aeon-skills/install-into-aeon.sh "$(pwd)"
```

### 3. Add GitHub secret

1. Settings → Secrets → Actions → `BDS_API_KEY` = `sk_live_...`
2. Get a key at https://bds-metering.powerloom.io/metering

### 4. Configure (optional)

```bash
cp templates/powerloom-bds.yml.example memory/powerloom-bds.yml
```

### 5. Enable in aeon.yml

```yaml
skills:
  powerloom-bds:
    enabled: true
    schedule: "*/15 * * * *"
```

### 6. Push

```bash
git add skills/powerloom-bds scripts/prefetch-bds.sh scripts/process-bds-skill.py scripts/postprocess-bds.sh
git commit -m "Sync powerloom-bds skill from aeon-skills"
git push
```

## Modes

| Mode | Aeon status |
|------|-------------|
| **whale-radar** | Shipped — deterministic prefetch processor |
| token-flow | Use OpenClaw `token-flow.mjs` until ported |
| pulse | Use `bds-agent trade` / OpenClaw `pulse.mjs` until ported |
| defi-analyst | Not deterministic in prefetch yet |

## Features

- **Whale Radar**: Large swaps from `allTrades` snapshot with epoch cursor
- **Verification**: CID in alerts when present in snapshot
- **Credits**: `X-BDS-Credit-Balance` logged in prefetch

## Related

- [Powerloom Docs](https://docs.powerloom.io/agents-and-bds/quickstart)
- [bds-agent CLI](https://github.com/powerloom/bds-agent-py)
- [OpenClaw skill](https://github.com/powerloom/powerloom-bds-univ3) — reference for token-flow / pulse scripts
- [Aeon Framework](https://github.com/aaronjmars/aeon)

## License

MIT
