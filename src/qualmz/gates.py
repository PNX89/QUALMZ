"""Three layers of testing, and a separate gate for each, because they fail differently.

An ML testing strategy that is one test suite is a strategy with one failure mode. These are
three, they answer three different questions, and each one stops the promotion on its own:

    DATA VALIDATION      is the feature frame the shape and range the model was built for?
                         Runs BEFORE the model sees anything, because a model scored on a frame
                         with a null column produces a number rather than an error.
    MODEL CORRECTNESS    does the model still produce the same predictions for a pinned set of
                         inputs? A golden set fails on ANY change, including an improvement,
                         which is the point: a change nobody intended is the one worth catching.
    PERFORMANCE          does a batch still fit its wall-clock and memory budget? A model that
                         got four times slower has changed, and no accuracy metric will say so.

WHERE THE BOUNDARY WITH A SIBLING IS. Great Expectations guards the feature frame INSIDE this
promotion pipeline, once a dataset is already trusted. Guarding a vendor's file at the door,
before anything is stored, is a different job in a different repository with a different tool,
and doing it twice would be two answers to one question.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateResult:
    """One layer's answer, with enough detail to act on a failure."""

    layer: str
    passed: bool
    detail: str


def golden_digest(predictions: Sequence[float]) -> str:
    """A hash over predictions rounded to a declared precision.

    ROUNDED ON PURPOSE, and the precision is part of the contract. Comparing raw floats makes
    the golden set fail on a BLAS version, a different CPU, or a summation order, which trains
    everybody to re-pin it without reading the diff. Rounding to six places keeps every change
    that could alter a decision and drops the ones that cannot.
    """
    payload = json.dumps([round(float(value), 6) for value in predictions], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def model_correctness(predictions: Sequence[float], *, expected_digest: str) -> GateResult:
    """The golden set. Fails on any change, including an improvement."""
    found = golden_digest(predictions)
    if found == expected_digest:
        return GateResult("model correctness", True, f"{len(predictions)} predictions unchanged")
    return GateResult(
        "model correctness",
        False,
        f"the golden set gives {found[:12]} and the pinned value is {expected_digest[:12]}. That "
        f"is a change in what this model predicts, and an improvement fails here too because an "
        f"unintended change is the one worth catching",
    )


def performance(work: Callable[[], Any], *, seconds_allowed: float, repeats: int = 3) -> GateResult:
    """A wall-clock budget per batch, measured as the BEST of several runs.

    THE BEST RATHER THAN THE MEAN, because a shared CI runner produces outliers in one direction
    only. Taking the mean makes the gate fire on a noisy neighbour, and a gate that fires on
    somebody else's build is a gate that gets its threshold raised until it never fires.
    """
    timings: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        work()
        timings.append(time.perf_counter() - started)
    best = min(timings)
    if best <= seconds_allowed:
        return GateResult(
            "performance", True, f"best of {repeats}: {best:.3f}s within {seconds_allowed}s"
        )
    return GateResult(
        "performance",
        False,
        f"best of {repeats} runs was {best:.3f}s against a budget of {seconds_allowed}s",
    )


def all_passed(results: Sequence[GateResult]) -> bool:
    return all(result.passed for result in results)
