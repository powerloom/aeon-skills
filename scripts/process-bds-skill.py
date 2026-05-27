#!/usr/bin/env python3
"""
Deterministic BDS skill processor for Aeon (whale-radar mode).

Runs in prefetch (full env) so GitHub Actions does not depend on the LLM
to advance the epoch cursor or deduplicate alerts.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from bds_normalize import normalize_bds_event  # noqa: E402

ROOT = SCRIPT_DIR.parent
CACHE = ROOT / ".bds-cache" / "latest.json"
STREAM_EVENTS = ROOT / ".bds-cache" / "stream-events.json"
CONFIG = ROOT / "memory" / "powerloom-bds.yml"
STATE = ROOT / "memory" / "powerloom-bds-state.json"
ALERTS = ROOT / ".bds-cache" / "alerts.json"
POOL_CACHE = ROOT / ".bds-cache" / "pool-metadata.json"
PENDING = ROOT / ".pending-notify"
ALERT_SEPARATOR = "\n━━━━━━━━━━━━━━━\n\n"


def _yaml_scalar(raw: str) -> str:
    """Strip inline YAML comments and surrounding quotes."""
    value = raw.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


def _load_yaml_mode() -> str:
    if not CONFIG.is_file():
        return "whale-radar"
    for line in CONFIG.read_text().splitlines():
        if line.strip().startswith("mode:"):
            return _yaml_scalar(line.split(":", 1)[1]) or "whale-radar"
    return "whale-radar"


def _load_threshold() -> float:
    if not CONFIG.is_file():
        return 25000.0
    in_thresholds = False
    for line in CONFIG.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("thresholds:"):
            in_thresholds = True
            continue
        if in_thresholds and stripped.startswith("whale_usd:"):
            raw = _yaml_scalar(stripped.split(":", 1)[1])
            try:
                return float(raw)
            except ValueError:
                return 25000.0
        if in_thresholds and stripped and not stripped.startswith("#") and ":" in stripped:
            key = stripped.split(":", 1)[0]
            if key not in ("whale_usd",):
                in_thresholds = False
    return 25000.0


def _load_state() -> dict:
    if not STATE.is_file():
        return {
            "lastStreamEpoch": None,
            "lastEmittedBlock": 0,
            "emittedFingerprints": [],
        }
    try:
        data = json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return {
            "lastStreamEpoch": None,
            "lastEmittedBlock": 0,
            "emittedFingerprints": [],
        }
    if not isinstance(data, dict):
        return {
            "lastStreamEpoch": None,
            "lastEmittedBlock": 0,
            "emittedFingerprints": [],
        }
    data.setdefault("emittedFingerprints", [])
    return data


def _save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def _fingerprint(trade: dict) -> str:
    log = trade.get("log") or {}
    tx = log.get("transactionHash") or trade.get("transactionHash") or ""
    bn = log.get("blockNumber") or trade.get("blockNumber") or 0
    return f"{tx}:{bn}"


def _trade_usd(trade: dict) -> float:
    data = trade.get("data") or {}
    for key in ("calculated_trade_amount_usd", "usd_amount"):
        val = data.get(key)
        if val is not None:
            try:
                return abs(float(val))
            except (TypeError, ValueError):
                pass
    try:
        t0 = abs(float(data.get("calculated_token0_amount") or 0))
        t1 = abs(float(data.get("calculated_token1_amount") or 0))
        return max(t0, t1)
    except (TypeError, ValueError):
        return 0.0


def _flatten_trades(body: dict) -> list[dict]:
    if not isinstance(body, dict):
        return []

    trade_data = body.get("tradeData")
    if isinstance(trade_data, dict):
        trades: list[dict] = []
        for pool_raw, pool_snap in trade_data.items():
            if not isinstance(pool_snap, dict):
                continue
            raw = pool_snap.get("trades") or []
            if not isinstance(raw, list):
                continue
            pool = str(pool_raw)
            for trade in raw:
                if not isinstance(trade, dict):
                    continue
                if not trade.get("poolAddress"):
                    trade = {**trade, "poolAddress": pool}
                trades.append(trade)
        if trades:
            return trades

    for key in ("trades",):
        val = body.get(key)
        if isinstance(val, list):
            return [t for t in val if isinstance(t, dict)]
    data = body.get("data")
    if isinstance(data, dict):
        val = data.get("trades")
        if isinstance(val, list):
            return [t for t in val if isinstance(t, dict)]
    return []


def _write_alerts(
    alerts: list[str],
    epoch_end: int | None,
    *,
    epoch_begin: int | None = None,
    epochs_processed: int = 0,
) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "alerts": alerts,
        "epoch_end": epoch_end,
        "epoch_begin": epoch_begin,
        "epochs_processed": epochs_processed,
    }
    ALERTS.write_text(json.dumps(payload, indent=2) + "\n")


def _load_snapshots() -> list[dict]:
    if STREAM_EVENTS.is_file():
        try:
            data = json.loads(STREAM_EVENTS.read_text())
        except (OSError, json.JSONDecodeError):
            data = None
        if isinstance(data, list):
            return [
                normalize_bds_event(item)
                for item in data
                if isinstance(item, dict) and not item.get("error")
            ]

    if not CACHE.is_file():
        return []

    try:
        body = json.loads(CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(body, dict) and not body.get("error"):
        return [normalize_bds_event(body)]
    return []


def _load_pool_cache() -> dict[str, dict]:
    if not POOL_CACHE.is_file():
        return {}
    try:
        raw = json.loads(POOL_CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for key, val in raw.items():
        if isinstance(key, str) and isinstance(val, dict):
            out[key.lower()] = val
    return out


def _fmt_usd(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def _fmt_amt(value: float) -> str:
    amount = abs(value)
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.2f}B"
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.2f}M"
    if amount >= 1:
        return f"{amount:,.4f}".rstrip("0").rstrip(".")
    return f"{amount:.8f}".rstrip("0").rstrip(".")


def _trade_direction(trade: dict) -> str:
    data = trade.get("data") or {}
    try:
        token0 = float(data.get("calculated_token0_amount") or 0)
    except (TypeError, ValueError):
        token0 = 0.0
    return "SELL" if token0 < 0 else "BUY"


def _project_slug(project_id: object) -> str:
    raw = str(project_id or "—")
    return raw.split(":", 1)[0] or raw


def _format_alert(
    trade: dict,
    usd: float,
    block: int | str | None,
    verification: dict | None,
    pool_info: dict | None,
) -> str:
    """OpenClaw whale-cron layout; plain text safe for Telegram legacy Markdown."""
    data = trade.get("data") or {}
    log = trade.get("log") or {}
    direction = _trade_direction(trade)
    side = "🟢" if direction == "BUY" else "🔴"

    pool_addr = str(trade.get("poolAddress") or "")
    if pool_info:
        token0 = pool_info.get("t0") or "???"
        token1 = pool_info.get("t1") or "???"
        fee = pool_info.get("fee") or "?"
    elif pool_addr:
        token0 = f"{pool_addr[:7]}…"
        token1 = "?"
        fee = "?"
    else:
        token0 = "???"
        token1 = "?"
        fee = "?"

    try:
        amount0 = abs(float(data.get("calculated_token0_amount") or 0))
        amount1 = abs(float(data.get("calculated_token1_amount") or 0))
    except (TypeError, ValueError):
        amount0 = 0.0
        amount1 = 0.0

    is_buy = direction == "BUY"
    bought_token = token0 if is_buy else token1
    sold_token = token1 if is_buy else token0
    bought_amt = amount0 if is_buy else amount1
    sold_amt = amount1 if is_buy else amount0

    wallet = data.get("sender") or data.get("recipient") or "—"
    wallet = str(wallet)
    short_wallet = (
        f"{wallet[:10]}…{wallet[-6:]}" if len(wallet) > 16 else wallet
    )

    tx_hash = log.get("transactionHash") or ""
    block_label = block if block is not None else "—"

    lines = [
        f"{side} 🐋 WHALE ALERT {side}",
        "",
        f"{side} {direction} {token0}/{token1} on Uniswap V3 ({fee})",
        f"💰 {_fmt_usd(usd)} swapped",
        "",
        f"▸ ⇢ {_fmt_amt(bought_amt)} {bought_token}",
        f"▸ ⇠ {_fmt_amt(sold_amt)} {sold_token}",
        f"▸ 🦊 {short_wallet}",
        f"▸ 📦 Block {block_label}",
    ]
    if tx_hash:
        lines.append(f"▸ 🔍 TX: https://etherscan.io/tx/{tx_hash}")

    if verification and verification.get("cid"):
        cid = str(verification.get("cid") or "")
        epoch_id = verification.get("epochId")
        project = _project_slug(verification.get("projectId"))
        lines.extend(
            [
                "",
                "✅ Verified on-chain:",
                f"  ├ CID: {cid[:28] + '…' if len(cid) > 28 else cid}",
                f"  ├ Epoch: {epoch_id if epoch_id is not None else '—'}",
                f"  └ Project: {project}",
            ],
        )

    return "\n".join(lines)


def main() -> int:
    mode = _load_yaml_mode()
    if mode != "whale-radar":
        print(f"process-bds-skill: skip mode={mode} (only whale-radar is deterministic)")
        return 0

    snapshots = _load_snapshots()
    if not snapshots:
        print("process-bds-skill: cache miss")
        return 0

    threshold = _load_threshold()
    state = _load_state()
    pool_cache = _load_pool_cache()
    emitted = list(state.get("emittedFingerprints") or [])
    emitted_set = set(emitted)

    alerts: list[str] = []
    max_block = int(state.get("lastEmittedBlock") or 0)
    epoch_begin: int | None = None
    epoch_end: int | None = None
    total_trades = 0

    for body in snapshots:
        epoch = body.get("epoch") if isinstance(body.get("epoch"), dict) else {}
        snap_begin = epoch.get("begin")
        snap_end = epoch.get("end")
        verification = body.get("verification") if isinstance(body.get("verification"), dict) else None

        try:
            if snap_begin is not None:
                begin_i = int(snap_begin)
                epoch_begin = begin_i if epoch_begin is None else min(epoch_begin, begin_i)
        except (TypeError, ValueError):
            pass
        try:
            if snap_end is not None:
                end_i = int(snap_end)
                epoch_end = end_i if epoch_end is None else max(epoch_end, end_i)
        except (TypeError, ValueError):
            pass

        trades = _flatten_trades(body)
        total_trades += len(trades)

        for trade in trades:
            usd = _trade_usd(trade)
            if usd < threshold:
                continue
            fp = _fingerprint(trade)
            if not fp or fp in emitted_set:
                continue
            trade_epoch = snap_end
            log = trade.get("log") or {}
            try:
                trade_epoch = int(log.get("blockNumber") or snap_end or 0) or snap_end
            except (TypeError, ValueError):
                pass
            pool_info = pool_cache.get(str(trade.get("poolAddress") or "").lower())
            alerts.append(
                _format_alert(trade, usd, trade_epoch, verification, pool_info),
            )
            emitted.append(fp)
            emitted_set.add(fp)
            try:
                max_block = max(max_block, int(log.get("blockNumber") or 0))
            except (TypeError, ValueError):
                pass

    while len(emitted) > 500:
        emitted.pop(0)

    if epoch_end is not None:
        state["lastStreamEpoch"] = epoch_end
    state["lastEmittedBlock"] = max_block
    state["emittedFingerprints"] = emitted
    state["last_run"] = datetime.now(tz=timezone.utc).isoformat()
    state["alerts_sent"] = len(alerts)
    state["mode"] = mode
    state["epochs_processed"] = len(snapshots)
    if epoch_begin is not None and epoch_end is not None:
        state["last_epoch_range"] = f"{epoch_begin}-{epoch_end}"
    _save_state(state)

    _write_alerts(
        alerts,
        epoch_end,
        epoch_begin=epoch_begin,
        epochs_processed=len(snapshots),
    )

    if alerts:
        PENDING.mkdir(parents=True, exist_ok=True)
        msg_path = PENDING / "bds-alerts.txt"
        msg_path.write_text(ALERT_SEPARATOR.join(alerts) + "\n")

    print(
        f"process-bds-skill: epochs={len(snapshots)} range={epoch_begin}-{epoch_end} "
        f"trades={total_trades} alerts={len(alerts)} cursor={state.get('lastStreamEpoch')}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
