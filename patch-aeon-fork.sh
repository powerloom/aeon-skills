#!/usr/bin/env bash
# Idempotent patches so powerloom-bds works on a vanilla Aeon fork.
# Called by install-into-aeon.sh; safe to re-run.

set -euo pipefail

AEON_ROOT="${1:-$(pwd)}"
WORKFLOW="$AEON_ROOT/.github/workflows/aeon.yml"
GITIGNORE="$AEON_ROOT/.gitignore"
AEON_YML="$AEON_ROOT/aeon.yml"

if [[ ! -f "$AEON_ROOT/aeon.yml" ]]; then
  echo "ERROR: $AEON_ROOT is not an Aeon repo (missing aeon.yml)" >&2
  exit 1
fi

patch_workflow() {
  [[ -f "$WORKFLOW" ]] || {
    echo "WARN: no $WORKFLOW — skip workflow patches (add BDS_API_KEY to prefetch env manually)"
    return 0
  }

  if ! grep -q 'BDS_API_KEY' "$WORKFLOW"; then
    python3 - "$WORKFLOW" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text().splitlines(keepends=True)
out = []
in_prefetch = False
inserted = False
for line in lines:
    out.append(line)
    if "- name: Run pre-fetch scripts" in line:
        in_prefetch = True
        continue
    if in_prefetch and not inserted and "REPLICATE_API_TOKEN:" in line:
        indent = line[: len(line) - len(line.lstrip())]
        out.append(f"{indent}BDS_API_KEY: ${{{{ secrets.BDS_API_KEY }}}}\n")
        inserted = True
    if in_prefetch and line.strip().startswith("run:") and "Run pre-fetch" not in line:
        in_prefetch = False
path.write_text("".join(out))
print(f"Patched prefetch env in {path}")
PY
  else
    echo "OK: BDS_API_KEY already in workflow"
  fi

  python3 - "$WORKFLOW" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
marker = '[[ "$f" == dashboard/outputs/* ]]'
entries = [
    "memory/powerloom-bds-state.json",
    "memory/powerloom-bds-pool-metadata.json",
]
if marker not in text:
    print(f"WARN: commit allowlist marker not found in {path}")
else:
    for entry in entries:
        if entry in text:
            continue
        text = text.replace(
            marker,
            f'[[ "$f" == {entry} ]] || {marker}',
            1,
        )
        print(f"Patched allowlist: {entry}")
    path.write_text(text)
PY
}

patch_gitignore() {
  if [[ ! -f "$GITIGNORE" ]]; then
    echo ".bds-cache/" >> "$GITIGNORE"
    echo "Added .bds-cache/ to new .gitignore"
    return 0
  fi
  if grep -q '\.bds-cache' "$GITIGNORE"; then
    echo "OK: .bds-cache/ already in .gitignore"
  else
    printf '\n# Powerloom BDS ephemeral prefetch cache\n.bds-cache/\n' >> "$GITIGNORE"
    echo "Added .bds-cache/ to .gitignore"
  fi
}

print_skill_snippet() {
  if grep -q 'powerloom-bds:' "$AEON_YML" 2>/dev/null; then
    echo "OK: powerloom-bds already in aeon.yml"
    return 0
  fi
  cat <<'EOF'

Add to aeon.yml under skills: (then set enabled: true)

  # --- Powerloom BDS (verified whale radar) ---
  powerloom-bds: { enabled: true, schedule: "*/5 * * * *" }

Optional threshold config:
  cp templates/powerloom-bds.yml.example memory/powerloom-bds.yml
  # edit thresholds.whale_usd (default in prefetch: 25000 if file missing)

EOF
}

patch_workflow
patch_gitignore
print_skill_snippet
