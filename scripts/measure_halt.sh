#!/usr/bin/env bash
# Run the promotion DAG twice, without an approval and then with one, and record what stopped.
#
# Usage:  scripts/measure_halt.sh
#
# WHAT IS MEASURED. A designed halt is only a halt if somebody has watched it stop something, and
# only useful if the same pipeline runs through when the condition is met. So both directions are
# executed against a real Airflow, and what is recorded is Airflow's own words: how many
# downstream tasks it skipped, and what state the run finished in.
#
# THE RUN STATE IS THE INTERESTING PART. A promotion that stopped for a human finishes SUCCESS,
# not FAILED. A pipeline that pages somebody because a promotion is waiting on approval is a
# pipeline whose alerts get muted within a fortnight.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/docs/evidence/halt"
WORK="${AIRFLOW_HOME:-$ROOT/target/airflow}"

mkdir -p "$OUT" "$WORK"
export AIRFLOW_HOME="$WORK"
export AIRFLOW__CORE__DAGS_FOLDER="$ROOT/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False

run_dag() {
  # `|| true` on purpose: a DAG run that stops is not a failure of this script, and letting
  # `set -e` abort here would hide the very outcome being measured.
  uv run --group orchestration airflow dags test promotion 2>&1 || true
}

echo "==> preparing the metadata database"
uv run --group orchestration airflow db migrate >/dev/null 2>&1

echo "==> 1. no approval recorded, which must stop before the alias moves"
WITHOUT="$(QUALMZ_APPROVED_BY= run_dag)"

echo "==> 2. an approval recorded, which must run through"
WITH="$(QUALMZ_APPROVED_BY=quelin run_dag)"

extract() {
  # Airflow's own words, not a summary of them.
  printf '%s\n' "$1" | grep -oE "tasks_skipped=[0-9]+|state=(success|failed)|Condition result is (True|False)" | sort -u | tr '\n' ' '
}

python3 - "$OUT/summary.json" "$(extract "$WITHOUT")" "$(extract "$WITH")" <<'PYTHON'
import json, sys

def parse(text):
    parts = text.split()
    return {
        "tasks_skipped": max(
            [int(p.split("=")[1]) for p in parts if p.startswith("tasks_skipped=")] or [0]
        ),
        "conditions": sorted({p for p in parts if p.startswith("Condition")} | set()),
        "run_state": next((p.split("=")[1] for p in parts if p.startswith("state=")), "unknown"),
    }

without, with_approval = parse(sys.argv[2]), parse(sys.argv[3])

if without["tasks_skipped"] < 1:
    print("nothing was skipped when no approval was recorded, so the halt did not halt",
          file=sys.stderr)
    raise SystemExit(1)
if with_approval["tasks_skipped"] != 0:
    print("something was skipped even with an approval recorded, so the pipeline cannot run "
          "through and the halt is a wall", file=sys.stderr)
    raise SystemExit(1)
if without["run_state"] != "success":
    print(f"the halted run finished {without['run_state']!r} rather than success. A promotion "
          f"waiting on a human is not an incident, and a pipeline that pages somebody for it "
          f"is one whose alerts get muted", file=sys.stderr)
    raise SystemExit(1)

with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump({"without_an_approval": without, "with_an_approval": with_approval}, handle, indent=2)
    handle.write("\n")
PYTHON

{
  echo "\$ airflow dags test promotion   # with no approval recorded"
  printf '%s\n' "$WITHOUT" | grep -oE "Condition result is False|Skipping downstream tasks|tasks_skipped=[0-9]+|state=success" | sed 's/^/  /' | sort -u
  echo
  echo "\$ QUALMZ_APPROVED_BY=quelin airflow dags test promotion"
  printf '%s\n' "$WITH" | grep -oE "Condition result is True|move_the_champion_alias|state=success" | sed 's/^/  /' | sort -u | head -4
  echo
  echo "The halted run finishes SUCCESS, not FAILED. A promotion waiting on a named human is not"
  echo "an incident, and a pipeline that pages somebody for one is a pipeline whose alerts get"
  echo "muted within a fortnight."
} > "$OUT/the-halt.txt"

cat "$OUT/the-halt.txt"
