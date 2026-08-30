"""Bad luck or a bug, as arithmetic, and the ways that arithmetic can be hollow."""

from __future__ import annotations

import json
import math
import pathlib
from typing import Any

import pytest

from qualmz.divergence import compare

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence" / "divergence"


def summary() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    return loaded


def test_the_planted_bug_fires_both_statistics() -> None:
    """If the obvious case did not fire, neither statistic has been shown working."""
    bug = summary()["cases"]["a bug"]
    assert bug["naive_alerts"] and bug["block_alerts"]
    assert abs(bug["block_t"]) >= summary()["threshold"]


def test_the_wandering_difference_fires_only_the_naive_one() -> None:
    """THE EXHIBIT. Two series with no drift between them, and one statistic calls it a bug.

    If the naive statistic stopped firing here, this exhibit would show nothing at all: it would
    be two tests agreeing on an easy case. Both halves are asserted for that reason.
    """
    luck = summary()["cases"]["bad luck"]
    assert luck["naive_alerts"], (
        "the naive standard error no longer calls this a bug, so the comparison has nothing to "
        "show and the generated series should be read rather than the threshold moved"
    )
    assert not luck["block_alerts"], (
        "the block standard error fired on a difference with no drift, which is the false alarm "
        "it exists to avoid"
    )


def test_the_block_standard_error_is_the_larger_one_in_both_cases() -> None:
    """The direction of the correction. If it were smaller, it would be finding MORE bugs."""
    for name, case in summary()["cases"].items():
        assert case["block_standard_error"] > case["naive_standard_error"], (
            f"{name}: the block standard error is smaller than the naive one, which would mean "
            f"the dependence makes the estimate more precise rather than less"
        )


def test_a_divergence_with_no_noise_at_all_alerts_rather_than_reporting_nothing() -> None:
    """THE MOST CERTAIN DIVERGENCE THERE IS, which used to be answered with 0.0 and silence.

    A live series that trails the simulation by the same amount every day has no dispersion in
    its daily difference, which is the shape of a missing fee or a constant slippage term. Both
    statistics divided by zero, both returned the value that means no evidence, and `alerts` was
    False. Adding 1e-12 to one single day of the same series gave a block t of 1e11 and an
    alert, so the verdict flipped on a grain of noise.
    """
    persistent = compare([0.001] * 100, [0.002] * 100, block_length=20)
    assert persistent.block_standard_error == 0.0
    assert persistent.mean_difference == pytest.approx(-0.001)
    assert persistent.block_t == -math.inf
    assert persistent.naive_t == -math.inf
    assert persistent.alerts(threshold=2.0), (
        "a live series behind the simulation by the same amount on every one of 100 days did "
        "not alert, which is the divergence this exists to find"
    )


def test_two_identical_series_report_nothing_rather_than_an_infinity() -> None:
    """The other half of the degenerate case, and the one 0.0 was the right answer to."""
    same = compare([0.001] * 100, [0.001] * 100, block_length=20)
    assert same.mean_difference == 0.0
    assert same.block_t == 0.0
    assert same.naive_t == 0.0
    assert not same.alerts(threshold=2.0)


def test_a_sample_too_short_for_blocks_raises_rather_than_answering() -> None:
    """Three blocks produce a number, and it is a number nobody should act on."""
    with pytest.raises(ValueError, match="not enough for a standard error"):
        compare([0.1] * 40, [0.2] * 40, block_length=20)


def test_two_series_of_different_lengths_raise() -> None:
    with pytest.raises(ValueError, match="different numbers of days"):
        compare([0.1] * 100, [0.2] * 90, block_length=10)


def test_a_block_of_one_is_refused_because_it_is_the_naive_estimate() -> None:
    with pytest.raises(ValueError, match="naive standard error under another name"):
        compare([0.1] * 100, [0.2] * 100, block_length=1)


def test_the_committed_series_reproduce_the_recorded_comparison() -> None:
    """RECOMPUTED FROM THE COMMITTED CSV, not read back from the summary beside it."""
    import csv

    path = REPO / "src" / "qualmz" / "data" / "paired_returns.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == summary()["days"]

    simulated = [float(row["simulated"]) for row in rows]
    for column, name in (("live_with_a_bug", "a bug"), ("live_with_bad_luck", "bad luck")):
        live = [float(row[column]) for row in rows]
        recomputed = compare(simulated, live, block_length=summary()["block_length"])
        recorded = summary()["cases"][name]
        assert round(recomputed.block_t, 3) == recorded["block_t"], (
            f"{name}: the committed series give a block t of {recomputed.block_t:.3f} and the "
            f"summary records {recorded['block_t']}"
        )
        assert round(recomputed.naive_t, 3) == recorded["naive_t"]


def test_the_transcript_says_no_capital_was_allocated() -> None:
    """The sentence that has to be on the page a reader sees, not only in a docstring."""
    text = (EVIDENCE / "bad-luck-or-a-bug.txt").read_text(encoding="utf-8")
    assert "No capital was ever allocated" in text
    assert "generated from seed" in text
