"""Three layers, and the ways each one can be a decoration."""

from __future__ import annotations

import time

import pytest

from qualmz import gates
from qualmz.gates import (
    GateResult,
    all_passed,
    golden_digest,
    model_correctness,
    performance,
)


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
    """Otherwise it fails on a BLAS version and everybody learns to re-pin without reading.

    A SIGN FLIP AT ZERO used to be the exception to this tolerance rather than an instance of
    it. `round(-1e-9, 6)` is `-0.0`, which `json.dumps` renders as the text `-0.0`, so a
    difference of 2e-9 either side of zero hashed differently while a difference of 8e-10 away
    from zero, asserted below, did not. A reordered summation is exactly the kind of change most
    likely to flip that sign, which is the failure the declared precision exists to prevent.
    """
    assert golden_digest([0.1234567891]) == golden_digest([0.1234567899])
    assert golden_digest([0.123456]) != golden_digest([0.123457])
    assert golden_digest([1e-9]) == golden_digest([-1e-9]), (
        "a sign flip 1e-9 either side of zero hashes differently, a thousand times below the "
        "six place precision this function declares"
    )


class Clock:
    """Stands in for the `time` module inside the gate, so its timings are stated not raced."""

    def __init__(self, durations: list[float]) -> None:
        readings: list[float] = []
        running = 0.0
        for duration in durations:
            readings += [running, running + duration]
            running += duration
        self.readings = iter(readings)

    def perf_counter(self) -> float:
        return next(self.readings)


def test_the_performance_gate_takes_the_best_run_rather_than_the_mean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shared runner produces outliers in one direction only.

    ON A STATED CLOCK, because the first version of this asserted the property in its name and
    could not tell it from the alternative it named. It slept 0.05s on one of three runs against
    a budget of 0.02s, which puts the mean at 0.0167s and inside the budget, so swapping `min`
    for the mean left the whole suite green, ten times out of ten on the named test alone. It
    also leant on the machine being quick enough for the other two runs to round to zero.

    So the timings are handed to the gate instead: a best of 0.001s inside the budget and a mean
    of 0.031s outside it, and the arithmetic that makes those two disagree is asserted rather
    than assumed.
    """
    budget = 0.02
    elapsed = [0.001, 0.09, 0.001]
    assert min(elapsed) < budget < sum(elapsed) / len(elapsed), (
        "these timings no longer separate the best from the mean, so this test has stopped "
        "discriminating between them whatever it is named"
    )

    monkeypatch.setattr(gates, "time", Clock(elapsed))
    result = performance(lambda: None, seconds_allowed=budget, repeats=3)
    assert result.passed, (
        "the gate failed a run whose fastest of three was inside the budget, which is a gate "
        "that fires on somebody else's noisy build"
    )
    assert "best of 3: 0.001s" in result.detail


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
