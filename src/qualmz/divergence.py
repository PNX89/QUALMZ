"""Live is underperforming the simulation. Bad luck, or a bug?

THE QUESTION THIS ANSWERS WITH A NUMBER. A simulated strategy and its live counterpart will
never agree exactly, and the useful question is never "do they differ" but "do they differ by
more than they should". That is arithmetic, and the arithmetic needs a standard error that
respects the fact that daily returns are not independent draws.

THE BLOCK-WISE STANDARD ERROR, and why the naive one is wrong here. Dividing the standard
deviation of the daily difference by the square root of the number of days assumes each day is
an independent observation. A strategy holds positions across days, so a difference that appears
on Monday is still there on Tuesday, and the naive standard error is therefore too small: it
finds a bug every time the two series wander apart for a fortnight. Splitting the sample into
non-overlapping blocks and taking the standard error ACROSS BLOCK MEANS keeps the dependence
inside a block, where it belongs.

WHAT THIS IS NOT. Neither series here is a record of anything traded. Both are generated, one
with a divergence introduced at a known point, so the alert can be shown firing on a difference
whose size and start date are known rather than argued about.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class Comparison:
    """How far apart two series are, in units of what their own noise can explain."""

    days: int
    blocks: int
    block_length: int
    mean_difference: float
    naive_standard_error: float
    block_standard_error: float

    @property
    def naive_t(self) -> float:
        if not self.naive_standard_error:
            return 0.0
        return self.mean_difference / self.naive_standard_error

    @property
    def block_t(self) -> float:
        if not self.block_standard_error:
            return 0.0
        return self.mean_difference / self.block_standard_error

    def alerts(self, *, threshold: float) -> bool:
        """The block statistic decides. The naive one is carried to show what it would say."""
        return abs(self.block_t) >= threshold


def compare(simulated: list[float], live: list[float], *, block_length: int) -> Comparison:
    """Compare two return series, with the standard error taken across blocks.

    Raises rather than returning something meaningless when there are too few blocks for a
    standard error to mean anything: three blocks produce a number, and it is a number nobody
    should act on.
    """
    if len(simulated) != len(live):
        raise ValueError("the two series cover different numbers of days")
    if block_length < 2:
        raise ValueError("a block of one is the naive standard error under another name")
    differences = [a - b for a, b in zip(simulated, live, strict=True)]
    blocks = [
        differences[start : start + block_length]
        for start in range(0, len(differences) - block_length + 1, block_length)
    ]
    if len(blocks) < 5:
        raise ValueError(
            f"{len(blocks)} blocks of {block_length} days is not enough for a standard error "
            f"anybody should act on"
        )

    means = [statistics.fmean(block) for block in blocks]
    return Comparison(
        days=len(differences),
        blocks=len(blocks),
        block_length=block_length,
        mean_difference=statistics.fmean(differences),
        naive_standard_error=statistics.stdev(differences) / len(differences) ** 0.5,
        block_standard_error=statistics.stdev(means) / len(means) ** 0.5,
    )
