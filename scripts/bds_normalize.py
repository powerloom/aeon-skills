"""Normalize BDS snapshot vs SSE stream event shapes to one processor format."""

from __future__ import annotations

from typing import Any


def normalize_bds_event(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Snapshot GET::

        {"epoch": {"begin": N, "end": N}, "tradeData": {...}, "verification": {...}}

    SSE stream::

        {"epoch": N, "snapshot": {"epoch": {...}, "tradeData": {...}}, "verification": {...}}
    """
    if not isinstance(raw, dict):
        return {}

    if isinstance(raw.get("tradeData"), dict):
        out = dict(raw)
    elif isinstance(raw.get("snapshot"), dict):
        out = dict(raw["snapshot"])
        verification = raw.get("verification")
        if isinstance(verification, dict):
            out["verification"] = verification
    else:
        return dict(raw)

    epoch = out.get("epoch")
    if not isinstance(epoch, dict):
        epoch_val = raw.get("epoch") if isinstance(raw.get("epoch"), int) else None
        if epoch_val is None and isinstance(out.get("epoch"), int):
            epoch_val = out.get("epoch")
        if epoch_val is not None:
            out["epoch"] = {"begin": epoch_val, "end": epoch_val}

    return out


def epoch_end(raw: dict[str, Any]) -> int | None:
    body = normalize_bds_event(raw)
    epoch = body.get("epoch")
    if not isinstance(epoch, dict):
        return None
    end = epoch.get("end")
    if end is None:
        end = epoch.get("begin")
    try:
        return int(end)
    except (TypeError, ValueError):
        return None


def epoch_begin(raw: dict[str, Any]) -> int | None:
    body = normalize_bds_event(raw)
    epoch = body.get("epoch")
    if not isinstance(epoch, dict):
        return None
    begin = epoch.get("begin")
    if begin is None:
        begin = epoch.get("end")
    try:
        return int(begin)
    except (TypeError, ValueError):
        return None
