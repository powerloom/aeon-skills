#!/bin/bash
# Post-process BDS skill: ensure epoch cursor persisted even if the LLM skipped state writes.

set -e

STATE_FILE="memory/powerloom-bds-state.json"
EPOCH_FILE=".bds-cache/epoch_range.txt"

if [ ! -f "$EPOCH_FILE" ]; then
    echo "postprocess-bds: no epoch_range.txt — skip"
    exit 0
fi

EPOCH_END=$(sed -n '2p' "$EPOCH_FILE")
if [ -z "$EPOCH_END" ]; then
    echo "postprocess-bds: empty epoch end — skip"
    exit 0
fi

python3 << PYTHON
import json
from pathlib import Path

state_path = Path("$STATE_FILE")
epoch_end = int("$EPOCH_END")

state = {}
if state_path.is_file():
    try:
        state = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError):
        state = {}

prev = state.get("lastStreamEpoch")
if prev is None or int(prev) < epoch_end:
    state["lastStreamEpoch"] = epoch_end
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"postprocess-bds: advanced cursor to {epoch_end}")
else:
    print(f"postprocess-bds: cursor already at {prev}")
PYTHON

exit 0
