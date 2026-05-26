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

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".bds-cache" / "latest.json"
CONFIG = ROOT / "memory" / "powerloom-bds.yml"
STATE = ROOT / "memory" / "powerloom-bds-state.json"
ALERTS = ROOT / ".bds-cache" / "alerts.json"
PENDING = ROOT / ".pending-notify"


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


def _write_alerts(alerts: list[str], epoch_end: int | None) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    ALERTS.write_text(json.dumps({"alerts": alerts, "epoch_end": epoch_end}, indent=2) + "\n")


def _format_alert(trade: dict, usd: float, epoch_end: int | None, verification: dict | None) -> str:
    log = trade.get("log") or {}
    pool = trade.get("poolAddress") or "?"
    tx = log.get("transactionHash") or "?"
    block = log.get("blockNumber") or "?"
    lines = [
        f"🐳 Whale alert: ${usd:,.2f}",
        f"Pool: {pool}",
        f"Epoch: {epoch_end or '?'}",
        f"Tx: {tx}",
        f"Block: {block}",
    ]
    if verification:
        cid = verification.get("cid")
        epoch_id = verification.get("epochId")
        project_id = verification.get("projectId")
        if cid and epoch_id is not None and project_id:
            lines.append("✅ Verified on-chain")
            lines.append(f"   cid: {cid}")
            lines.append(f"   project: {project_id}")
            lines.append(f"   epoch_id: {epoch_id}")
    return "\n".join(lines)


def main() -> int:
    mode = _load_yaml_mode()
    if mode != "whale-radar":
        print(f"process-bds-skill: skip mode={mode} (only whale-radar is deterministic)")
        return 0

    if not CACHE.is_file():
        print("process-bds-skill: cache miss")
        return 0

    try:
        body = json.loads(CACHE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"process-bds-skill: invalid cache: {exc}")
        return 1

    if body.get("error"):
        print(f"process-bds-skill: fetch error in cache: {body.get('error')}")
        return 0

    threshold = _load_threshold()
    state = _load_state()
    emitted = list(state.get("emittedFingerprints") or [])
    emitted_set = set(emitted)

    epoch = body.get("epoch") if isinstance(body.get("epoch"), dict) else {}
    epoch_begin = epoch.get("begin")
    epoch_end = epoch.get("end")
    verification = body.get("verification") if isinstance(body.get("verification"), dict) else None

    trades = _flatten_trades(body)
    alerts: list[str] = []
    max_block = int(state.get("lastEmittedBlock") or 0)

    for trade in trades:
        usd = _trade_usd(trade)
        if usd < threshold:
            continue
        fp = _fingerprint(trade)
        if not fp or fp in emitted_set:
            continue
        alerts.append(_format_alert(trade, usd, epoch_end, verification))
        emitted.append(fp)
        emitted_set.add(fp)
        log = trade.get("log") or {}
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
    if epoch_begin is not None and epoch_end is not None:
        state["last_epoch_range"] = f"{epoch_begin}-{epoch_end}"
    _save_state(state)

    _write_alerts(alerts, epoch_end)

    if alerts:
        PENDING.mkdir(parents=True, exist_ok=True)
        msg_path = PENDING / "bds-alerts.txt"
        msg_path.write_text("\n\n".join(alerts) + "\n")

    print(
        f"process-bds-skill: epoch_end={epoch_end} trades={len(trades)} "
        f"alerts={len(alerts)} cursor={state.get('lastStreamEpoch')}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
