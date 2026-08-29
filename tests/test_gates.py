"""Three layers, and the ways each one can be a decoration."""

from __future__ import annotations

import time

from qualmz.gates import GateResult, all_passed, golden_digest, model_correctness, performance


def test_the_golden_set_passes_on_identical_predictions() -> None:
    predictions = [0.1, 0.2, 0.30000001]
    assert model_correctness(predictions, expected_digest=golden_digest(predictions)).passed


def test_the_golden_set_fails_on_an_improvement_as_well_as_a_regression() -> None:
    """The property that makes it a correctness gate rather than a quality one."""
    pinned = golden_digest([0.1, 0.2, 0.3])
    for changed in ([0.1, 0.2, 0.4], [0.1, 0.2, 0.29]):
        result = model_correctness(changed, expected_digest=pinned)
        assert not result.passed
        assert "an improvement fails here too" in result.detail


def test_the_golden_set_tolerates_a_difference_below_the_declared_precision() -> None:
    """Otherwise it fails on a BLAS version and everybody learns to re-pin without reading."""
    assert golden_digest([0.1234567891]) == golden_digest([0.1234567899])
    assert golden_digest([0.123456]) != golden_digest([0.123457])


def test_the_performance_gate_takes_the_best_run_rather_than_the_mean() -> None:
    """A shared runner produces outliers in one direction only.

    The work here is fast, and one call is made deliberately slow. Taking the mean would fail;
    taking the best does not, which is the behaviour a gate needs on somebody else's noisy build.
    """
    calls = {"n": 0}

    def work() -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            time.sleep(0.05)

    assert performance(work, seconds_allowed=0.02, repeats=3).passed


def test_the_performance_gate_fails_when_every_run_is_over_budget() -> None:
    def slow() -> None:
        time.sleep(0.03)

    result = performance(slow, seconds_allowed=0.005, repeats=2)
    assert not result.passed
    assert "against a budget" in result.detail


def test_one_failing_layer_fails_the_set() -> None:
    results = [
        GateResult("data validation", True, ""),
        GateResult("model correctness", False, ""),
        GateResult("performance", True, ""),
    ]
    assert all_passed(results) is False
    assert all_passed([r for r in results if r.passed]) is True
