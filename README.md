# Powerloom BDS — Aeon Skill

An [Aeon](https://github.com/aaronjmars/aeon) skill that fetches verified on-chain data from [Powerloom BDS](https://docs.powerloom.io/agents-and-bds/quickstart) and dispatches actionable alerts.

**Every alert carries an on-chain verification CID** — the data is consensus-finalized by the DSV network, not trust-the-vendor.

## Features

- **Whale Radar**: Alert on large swaps across Uniswap V3 pools
- **Token Flow**: Track multi-pool token movements
- **Pulse**: Confluence signals (price + volume + flow) with cooldown
- **DeFi Analyst**: Narrated market summaries with verification probes

## Quick Start

### 1. Fork Aeon

```bash
git clone https://github.com/aaronjmars/aeon
cd aeon
```

### 2. Install this skill

If this repo is published (e.g., `powerloom/aeon-skills`):

```bash
./add-skill powerloom/aeon-skills powerloom-bds
```

Or copy manually:
```bash
cp -r /path/to/powerloom-aeon-skill/skills/powerloom-bds skills/
cp /path/to/powerloom-aeon-skill/scripts/prefetch-bds.sh scripts/
```

### 3. Configure

Create `memory/powerloom-bds.yml`:
```bash
cp templates/powerloom-bds.yml.example memory/powerloom-bds.yml
# Edit to set your pools and thresholds
```

### 4. Add GitHub secret

1. Go to your fork's Settings → Secrets and variables → Actions
2. Add `BDS_API_KEY` with your `sk_live_...` key
3. Get your key at https://bds-metering.powerloom.io/metering

### 5. Enable in aeon.yml

```yaml
skills:
  powerloom-bds:
    enabled: true
    schedule: "*/15 * * * *"  # Every 15 minutes
```

### 6. Push and verify

```bash
git add .
git commit -m "Add powerloom-bds skill"
git push
```

Run `./onboard --remote` to verify everything is wired up.

## Modes

### whale-radar (default)

Alerts on whale swaps above threshold:

```
🐳 Whale alert: WETH → USDC  $1,312,000

Pool: 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640
Epoch: 24785842
Tx: 0xa1b2...
✅ Verified on-chain
   cid: bafkrei...
   project: allTradesSnapshot:0x26c4...
```

### token-flow

Tracks a token across all configured pools:

```
📊 Token Flow: USDC

Pool: USDC/WETH 0.05% — Net: +$125K (68% buy)
Pool: USDC/WETH 0.3% — Net: -$42K (55% sell)
Total: +$83K inflow across 2 pools
```

### pulse

Confluence of signals → direction call:

```
⚡ PULSE: LONG WETH

Signals: Price +0.5%, Volume 3.2×, Flow 62% buy
Window: 5 min | Confidence: HIGH
```

### defi-analyst

Narrated market summary:

```
📈 DeFi Brief — 2026-05-18 12:00 UTC

ETH: $3,842 (+0.3%) | Gas: 25 gwei

Top flows: USDC inflows to WETH pools, whale activity in 0.05% pool
Notable: 3 alerts this hour, largest $1.3M swap

🔍 Verification probe: epoch 24785842 ✓
```

## Configuration Reference

```yaml
mode: whale-radar  # whale-radar | token-flow | pulse | defi-analyst

pools:
  - address: "0x..."  # Uniswap V3 pool address
    name: "Pool name"

thresholds:
  whale_usd: 25000        # Min USD for whale alert
  volume_spike_mult: 2.5  # Volume burst multiplier
  price_move_pct: 0.4     # Price movement %
  flow_imbalance_pct: 35  # Flow imbalance %

pulse:
  window_minutes: 5
  cooldown_minutes: 10

analyst:
  report_cadence: hourly
  include_verification_probe: true
```

## Verification

Every alert includes a CID you can verify on-chain:

```bash
cast call 0xa1100CB00Acd3cA83a7C8F4DAA42701D1Eaf4A6c \
  "maxSnapshotsCid(address,string,uint256)(string,uint8)" \
  0x4198Bf81B55EE4Af6f9Ddc176F8021960813f641 \
  "<projectId>" \
  <epoch> \
  --rpc-url https://rpc-v2.powerloom.network
```

## Requirements

- **BDS_API_KEY** — GitHub secret with your `sk_live_...` key
- **Config file** — `memory/powerloom-bds.yml`
- **Notification channels** — Set Telegram/Discord/Slack secrets in Aeon

## Credits

BDS data is metered. Each request burns credits. Check your balance:
- In response header: `X-BDS-Credit-Balance`
- At https://bds-metering.powerloom.io/metering

Sign up for free credits at the metering page. Paid plans available in POWER or USDC.

## Related

- [Powerloom Docs](https://docs.powerloom.io/agents-and-bds/quickstart)
- [bds-agent CLI](https://pypi.org/project/bds-agent/)
- [Aeon Framework](https://github.com/aaronjmars/aeon)

## License

MIT
