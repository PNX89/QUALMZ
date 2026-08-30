"""The promotion gate: what has to be true before a challenger becomes the champion.

THE GATE REFUSES ON A HASH IT DID NOT PRODUCE. A challenger only takes the alias when its result
and the incumbent's RE-SCORED result carry the same data-provenance hash. That hash is minted
elsewhere, by the repository that admits the dataset, and this one consumes it and never computes
one. Comparing two scores computed on two different data versions is the commonest way a
promotion is wrong while every number in it is right.

THE INCUMBENT IS RE-SCORED RATHER THAN REMEMBERED. A stored score from a previous run was
computed on whatever data existed then, so comparing a fresh challenger against it compares two
things that differ in more than the model. The gate requires a score for the incumbent carrying
the same hash as the challenger's, which in practice means running it again.

AN ALIAS, NOT A STAGE. `set_registered_model_alias` rather than `transition_model_version_stage`.
Measured on MLflow 3.15.2: the stage API still exists and still works, and calling it prints
"deprecated since 2.9.0. Model registry stages will be removed in a future major release". So
this is a choice rather than a necessity, which is the reason it is written down.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Every reason a promotion can be refused. Each one is a sentence a person can act on rather
#: than a code, because the audience for a refusal is the researcher whose model it was.
REFUSALS = {
    "provenance": (
        "the challenger and the incumbent were scored on different data versions, so the "
        "comparison is between two things that differ in more than the model"
    ),
    "unscored": "the incumbent has no score carrying the challenger's data version",
    "budget": "the configuration was never recorded as a look, so the holdout was read outside "
    "the ledger",
    "worse": "the challenger did not beat the incumbent",
    "human": "a named human has not approved this promotion",
}


@dataclass(frozen=True)
class Result:
    """One model's score, and the data version it was computed on."""

    model: str
    version: int
    score: float
    provenance_sha256: str
    configuration_hash: str

    def __post_init__(self) -> None:
        try:
            is_a_sha256 = len(bytes.fromhex(self.provenance_sha256)) == 32
        except ValueError:
            is_a_sha256 = False
        if not is_a_sha256:
            raise ValueError(
                f"{self.provenance_sha256!r} is not a SHA-256. This repository CONSUMES a "
                f"provenance hash minted where the dataset was admitted, and a value that is "
                f"not one means something local was substituted for it"
            )


@dataclass(frozen=True)
class Decision:
    """What the gate decided, and every reason it did not promote."""

    promote: bool
    refusals: tuple[str, ...]

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(REFUSALS[key] for key in self.refusals)


def decide(
    challenger: Result,
    incumbent: Result | None,
    *,
    look_recorded: bool,
    approved_by: str | None,
) -> Decision:
    """Every gate, evaluated, and all the failures returned rather than the first one.

    RETURNING ALL OF THEM IS DELIBERATE. A gate that short-circuits on the first failure sends a
    researcher round the loop once per problem, and each loop is another look at the holdout.
    """
    refusals: list[str] = []

    if incumbent is None:
        refusals.append("unscored")
    elif incumbent.provenance_sha256 != challenger.provenance_sha256:
        refusals.append("provenance")
    elif challenger.score <= incumbent.score:
        refusals.append("worse")

    if not look_recorded:
        refusals.append("budget")
    if not approved_by:
        refusals.append("human")

    return Decision(promote=not refusals, refusals=tuple(refusals))
