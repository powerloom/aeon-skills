#!/usr/bin/env python3
"""
Fetch BDS allTrades snapshots epoch-by-epoch (recommended API path).

Uses GET /mpp/snapshot/allTrades/{block_number} — not SSE.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from bds_agent.client import BdsClientError, fetch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from bds_normalize import epoch_begin, epoch_end, normalize_bds_event  # noqa: E402
from bds_rate_limit import BdsRateLimiter, DEFAULT_RPM, fetch_throttled  # noqa: E402

ROOT = SCRIPT_DIR.parent
CACHE_DIR = ROOT / ".bds-cache"
POOL_CACHE_PATH = ROOT / "memory" / "powerloom-bds-pool-metadata.json"
MAX_EPOCHS = int(os.environ.get("BDS_MAX_EPOCHS_PER_RUN", "100"))
# Blocks within this distance of BDS tip: 404 means "not finalized yet" — stop catch-up.
# Farther behind tip: 404 is a gap — skip block and keep scanning forward.
FINALIZATION_BUFFER = int(os.environ.get("BDS_FINALIZATION_BUFFER", "5"))
# Upper bound on HTTP attempts per run (successful + skipped 404s).
MAX_BLOCK_ATTEMPTS = int(
    os.environ.get("BDS_MAX_BLOCK_ATTEMPTS", str(max(MAX_EPOCHS * 10, 500))),
)
POOL_METADATA_CONCURRENCY = int(os.environ.get("BDS_POOL_METADATA_CONCURRENCY", "2"))


def _load_pool_cache() -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if not POOL_CACHE_PATH.is_file():
        return cache
    try:
        loaded = json.loads(POOL_CACHE_PATH.read_text())
        if isinstance(loaded, dict):
            cache = {
                str(k).lower(): v
                for k, v in loaded.items()
                if isinstance(v, dict)
            }
    except (OSError, json.JSONDecodeError):
        pass
    return cache


def _save_pool_cache(cache: dict[str, dict]) -> None:
    POOL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    POOL_CACHE_PATH.write_text(json.dumps(cache, indent=2) + "\n")
    # Same-run processor reads .bds-cache copy (ephemeral dir wiped each prefetch).
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "pool-metadata.json").write_text(json.dumps(cache, indent=2) + "\n")


def _collect_pool_addresses(snapshots: list[dict]) -> set[str]:
    pools: set[str] = set()
    for snap in snapshots:
        trade_data = snap.get("tradeData")
        if not isinstance(trade_data, dict):
            continue
        for pool_raw in trade_data:
            pool = str(pool_raw).lower()
            if pool.startswith("0x") and len(pool) >= 42:
                pools.add(pool)
    return pools


def _pool_info_from_metadata(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    token0 = data.get("token0") if isinstance(data.get("token0"), dict) else {}
    token1 = data.get("token1") if isinstance(data.get("token1"), dict) else {}
    sym0 = token0.get("symbol")
    sym1 = token1.get("symbol")
    if not sym0 or not sym1:
        return None
    try:
        fee_bps = int(data.get("fee") or 0)
    except (TypeError, ValueError):
        fee_bps = 0
    if fee_bps >= 10000:
        fee = f"{fee_bps / 10000:g}%"
    elif fee_bps >= 100:
        fee = f"{fee_bps / 100:g}%"
    else:
        fee = f"{fee_bps:g}%"
    return {"t0": str(sym0), "t1": str(sym1), "fee": fee}


async def _resolve_pool_metadata(
    limiter: BdsRateLimiter,
    base_url: str,
    api_key: str,
    snapshots: list[dict],
) -> None:
    cache = _load_pool_cache()
    needed = _collect_pool_addresses(snapshots)
    missing = sorted(p for p in needed if p not in cache)
    if not missing:
        _save_pool_cache(cache)
        print(f"Pool metadata cache: {len(cache)} pools (0 fetched this run)")
        return

    sem = asyncio.Semaphore(max(1, POOL_METADATA_CONCURRENCY))
    fetched = 0
    failed = 0

    async def _fetch_one(pool: str) -> None:
        nonlocal fetched, failed
        async with sem:
            try:
                result = await fetch_throttled(
                    limiter,
                    base_url,
                    f"/mpp/pool/{pool}/metadata",
                    api_key,
                )
                info = _pool_info_from_metadata(result.data)
                if info:
                    cache[pool] = info
                    fetched += 1
            except BdsClientError as exc:
                failed += 1
                if failed <= 5 or failed % 20 == 0:
                    print(f"WARN: pool metadata failed for {pool}: {exc}")

    print(
        f"Pool metadata: {len(missing)} missing, "
        f"concurrency={POOL_METADATA_CONCURRENCY}, rpm cap={DEFAULT_RPM}",
    )
    await asyncio.gather(*[_fetch_one(pool) for pool in missing])
    _save_pool_cache(cache)
    print(
        f"Pool metadata cache: {len(cache)} pools "
        f"({fetched} fetched, {failed} failed this run)",
    )


async def _latest_epoch(limiter: BdsRateLimiter, base_url: str, api_key: str) -> int | None:
    result = await fetch_throttled(limiter, base_url, "/mpp/snapshot/allTrades", api_key)
    return epoch_end(result.data) or epoch_begin(result.data)


async def _fetch_epoch(
    limiter: BdsRateLimiter,
    base_url: str,
    api_key: str,
    block: int,
) -> dict | None:
    result = await fetch_throttled(
        limiter,
        base_url,
        f"/mpp/snapshot/allTrades/{block}",
        api_key,
    )
    return normalize_bds_event(result.data)


async def main() -> int:
    base_url = os.environ.get("BDS_BASE_URL", "https://bds.powerloom.io/api")
    api_key = os.environ.get("BDS_API_KEY")
    if not api_key:
        print("ERROR: BDS_API_KEY not set")
        return 1

    from_epoch_raw = os.environ.get("FROM_EPOCH", "").strip()
    start_epoch = int(from_epoch_raw) if from_epoch_raw else None

    limiter = BdsRateLimiter(DEFAULT_RPM)
    print(f"BDS rate limit: {DEFAULT_RPM} req/min (set BDS_RATE_LIMIT_RPM to match your key)")

    tip = await _latest_epoch(limiter, base_url, api_key)
    if tip is None:
        print("ERROR: could not resolve latest finalized epoch")
        return 1

    if start_epoch is None:
        start_epoch = tip
        print(f"No cursor — fetching latest epoch {tip}")
    else:
        print(f"Catch-up: epochs {start_epoch} → {tip} (max {MAX_EPOCHS} per run)")

    if start_epoch > tip:
        print(f"Already caught up (cursor ahead of tip: {start_epoch - 1} >= {tip})")
        snapshots: list[dict] = []
    else:
        snapshots = []
        block = start_epoch
        attempts = 0
        skipped_gaps = 0
        while block <= tip and len(snapshots) < MAX_EPOCHS and attempts < MAX_BLOCK_ATTEMPTS:
            attempts += 1
            try:
                snap = await _fetch_epoch(limiter, base_url, api_key, block)
            except BdsClientError as exc:
                msg = str(exc)
                if "404" in msg or "not found" in msg.lower():
                    near_tip = block >= tip - FINALIZATION_BUFFER
                    if near_tip:
                        print(
                            f"Epoch {block} not finalized yet (tip={tip}) — "
                            f"stopping after {len(snapshots)} snapshot(s)",
                        )
                        break
                    skipped_gaps += 1
                    if skipped_gaps <= 3 or skipped_gaps % 50 == 0:
                        print(f"WARN: no snapshot at block {block} (404) — skipping gap")
                    block += 1
                    continue
                print(f"ERROR epoch {block}: {exc}")
                return 1

            if snap:
                snapshots.append(snap)
            block += 1

        if attempts >= MAX_BLOCK_ATTEMPTS and len(snapshots) < MAX_EPOCHS and block <= tip - FINALIZATION_BUFFER:
            print(
                f"WARN: hit max block attempts ({MAX_BLOCK_ATTEMPTS}) with "
                f"{len(snapshots)} snapshot(s); will resume from cursor next run",
            )

        if snapshots:
            begins = [epoch_begin(s) for s in snapshots]
            ends = [epoch_end(s) for s in snapshots]
            begins = [b for b in begins if b is not None]
            ends = [e for e in ends if e is not None]
            gap_note = f", {skipped_gaps} gap(s) skipped" if skipped_gaps else ""
            print(
                f"Fetched {len(snapshots)} snapshot(s): "
                f"{min(begins) if begins else '?'} - {max(ends) if ends else '?'}"
                f"{gap_note}",
            )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "stream-events.json").write_text(json.dumps(snapshots, indent=2) + "\n")

    if snapshots:
        (CACHE_DIR / "latest.json").write_text(json.dumps(snapshots[-1], indent=2) + "\n")
        begins = [epoch_begin(s) for s in snapshots]
        ends = [epoch_end(s) for s in snapshots]
        begins = [b for b in begins if b is not None]
        ends = [e for e in ends if e is not None]
        if ends:
            (CACHE_DIR / "epoch_range.txt").write_text(
                f"{min(begins) if begins else min(ends)}\n{max(ends)}\n",
            )
        await _resolve_pool_metadata(limiter, base_url, api_key, snapshots)
    else:
        print("WARN: no snapshots fetched this run")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
