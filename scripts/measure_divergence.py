"""Two paired series, generated deterministically, and what each standard error says about them.

    uv run python scripts/measure_divergence.py

TWO CASES, BECAUSE ONE PROVES NOTHING.

    A BUG. The live series carries a persistent drag from a known day. Both statistics should
    fire, and the exhibit is that they do.

    BAD LUCK. The two series differ only by noise that WANDERS: a difference with no drift at
    all, but with memory, which is what an ordinary run of good and bad weeks looks like. The
    naive standard error treats each day as an independent observation and calls this a bug.
    The block standard error does not.

NEITHER SERIES IS A RECORD OF ANYTHING TRADED. Both are generated from a fixed seed, no capital
was ever allocated, and the divergence in the first case is introduced by this file at a day
this file chooses. That is the point: the alert can be shown firing on a difference whose size
and start are known rather than argued about.
"""

from __future__ import annotations

import json
import pathlib
import random
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qualmz.divergence import compare  # noqa: E402

OUT = ROOT / "docs" / "evidence" / "divergence"
DATA = ROOT / "src" / "qualmz" / "data"

SEED = 20260829
DAYS = 500
BLOCK_LENGTH = 20
THRESHOLD = 2.0
BREAK_ON = 300
DRAG = 0.0012

#: How strongly today's difference carries into tomorrow's, in the bad luck case. Zero would be
#: independent noise, where the two standard errors agree and the exhibit shows nothing.
MEMORY = 0.9


def series() -> tuple[list[float], list[float], list[float]]:
    rng = random.Random(SEED)
    simulated = [rng.gauss(0.0004, 0.01) for _ in range(DAYS)]

    with_bug = list(simulated)
    with_bug[BREAK_ON:] = [value - DRAG for value in with_bug[BREAK_ON:]]

    # A difference with memory and no drift: the same expected value as the simulation, drifting
    # apart and back the way two implementations of one strategy actually do.
    wandering = []
    carried = 0.0
    for _ in range(DAYS):
        carried = MEMORY * carried + rng.gauss(0.0, 0.0008)
        wandering.append(carried)
    with_bad_luck = [value - drift for value, drift in zip(simulated, wandering, strict=True)]

    return simulated, with_bug, with_bad_luck


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    simulated, with_bug, with_bad_luck = series()

    cases = {
        "a bug": compare(simulated, with_bug, block_length=BLOCK_LENGTH),
        "bad luck": compare(simulated, with_bad_luck, block_length=BLOCK_LENGTH),
    }

    summary: dict[str, Any] = {
        "seed": SEED,
        "days": DAYS,
        "block_length": BLOCK_LENGTH,
        "threshold": THRESHOLD,
        "drag_from_day": BREAK_ON,
        "drag_per_day": DRAG,
        "cases": {
            name: {
                "mean_difference": round(case.mean_difference, 8),
                "naive_standard_error": round(case.naive_standard_error, 8),
                "block_standard_error": round(case.block_standard_error, 8),
                "naive_t": round(case.naive_t, 3),
                "block_t": round(case.block_t, 3),
                "naive_alerts": abs(case.naive_t) >= THRESHOLD,
                "block_alerts": case.alerts(threshold=THRESHOLD),
                "blocks": case.blocks,
            }
            for name, case in cases.items()
        },
    }

    cases_recorded: dict[str, dict[str, Any]] = summary["cases"]
    bug, luck = cases_recorded["a bug"], cases_recorded["bad luck"]
    if not (bug["naive_alerts"] and bug["block_alerts"]):
        print(
            "the planted bug did not fire both statistics, so neither is shown working",
            file=sys.stderr,
        )
        return 1
    if not luck["naive_alerts"]:
        print(
            "the naive statistic did not fire on the wandering difference, so this exhibit no "
            "longer shows what the block standard error is FOR and the memory should be read "
            "rather than the threshold relaxed",
            file=sys.stderr,
        )
        return 1
    if luck["block_alerts"]:
        print(
            "the block statistic fired on a difference with no drift, which is the false alarm "
            "it exists to avoid",
            file=sys.stderr,
        )
        return 1

    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    with (DATA / "paired_returns.csv").open("w", encoding="utf-8") as handle:
        print("day,simulated,live_with_a_bug,live_with_bad_luck", file=handle)
        for day, (a, b, c) in enumerate(zip(simulated, with_bug, with_bad_luck, strict=True)):
            print(f"{day},{a:.10f},{b:.10f},{c:.10f}", file=handle)

    with (OUT / "bad-luck-or-a-bug.txt").open("w", encoding="utf-8") as handle:
        print("$ uv run python scripts/measure_divergence.py", file=handle)
        print(file=handle)
        print(
            f"{DAYS} days, generated from seed {SEED}. No capital was ever allocated and neither",
            file=handle,
        )
        print("series is a record of anything traded.", file=handle)
        print(file=handle)
        print(
            f"  {'':<12}{'mean diff':>12}{'naive t':>10}{'block t':>10}{'  alerts':>12}",
            file=handle,
        )
        for name, case in cases_recorded.items():
            verdict = []
            if case["naive_alerts"]:
                verdict.append("naive")
            if case["block_alerts"]:
                verdict.append("block")
            print(
                f"  {name:<12}{case['mean_difference']:>12.6f}{case['naive_t']:>10.2f}"
                f"{case['block_t']:>10.2f}   {' and '.join(verdict) or 'neither'}",
                file=handle,
            )
        print(file=handle)
        print(
            "The second row is two series with no drift between them at all, differing only by",
            file=handle,
        )
        print(
            "noise that wanders. The naive standard error treats each day as an independent",
            file=handle,
        )
        print(
            f"observation and reports t = {luck['naive_t']:.2f}, which is a bug. Taking the "
            f"standard error",
            file=handle,
        )
        print(
            f"across {luck['blocks']} non-overlapping blocks instead gives "
            f"{luck['block_t']:.2f}, which is a fortnight of bad weeks.",
            file=handle,
        )
    print((OUT / "bad-luck-or-a-bug.txt").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
