"""The gate, and the four ways a promotion can look right and be wrong."""

from __future__ import annotations

import pytest

from qualmz.promotion import Decision, Result, decide

HASH_A = "a" * 64
HASH_B = "b" * 64


def result(score: float, provenance: str = HASH_A, model: str = "momentum") -> Result:
    return Result(
        model=model,
        version=1,
        score=score,
        provenance_sha256=provenance,
        configuration_hash="c" * 64,
    )


def test_a_better_challenger_on_the_same_data_with_a_look_and_a_human_promotes() -> None:
    decision = decide(result(0.61), result(0.55), look_recorded=True, approved_by="quelin")
    assert decision.promote is True
    assert decision.refusals == ()


def test_a_better_score_on_a_different_data_version_is_refused() -> None:
    """The refusal this gate exists for, and the one where every number involved is correct."""
    decision = decide(
        result(0.61, HASH_A), result(0.55, HASH_B), look_recorded=True, approved_by="quelin"
    )
    assert decision.promote is False
    assert "provenance" in decision.refusals
    assert "differ in more than the model" in " ".join(decision.reasons)


def test_an_unscored_incumbent_is_refused_rather_than_treated_as_zero() -> None:
    """Treating a missing incumbent as a score of zero promotes anything at all."""
    decision = decide(result(0.61), None, look_recorded=True, approved_by="quelin")
    assert decision.promote is False
    assert "unscored" in decision.refusals


def test_a_challenger_that_did_not_beat_the_incumbent_is_refused() -> None:
    """DRIVEN THROUGH THE GATE, because the wording of a refusal is not the enforcement of it.

    The only other mention of this refusal built a Decision by hand, so the branch that produces
    it was reached by nothing. Deleting the branch promoted a challenger scoring 0.10 against an
    incumbent scoring 0.99, with the whole suite green.

    THE TIE IS THE SECOND CASE, and for the same reason. Weakening the comparison from `<=` to
    `<` is invisible to a test that only tries a clear loser, and a dead heat promoting means a
    rewritten model that measures identically takes the alias off the one already in service.
    """
    for challenger, incumbent in ((0.10, 0.99), (0.55, 0.55)):
        decision = decide(
            result(challenger), result(incumbent), look_recorded=True, approved_by="quelin"
        )
        assert decision.promote is False, (
            f"a challenger scoring {challenger} was promoted over an incumbent scoring {incumbent}"
        )
        assert "worse" in decision.refusals
        assert "did not beat the incumbent" in " ".join(decision.reasons)


def test_a_promotion_without_a_recorded_look_is_refused() -> None:
    """A score computed off the ledger is a holdout read outside the budget."""
    decision = decide(result(0.61), result(0.55), look_recorded=False, approved_by="quelin")
    assert decision.promote is False
    assert "budget" in decision.refusals


def test_a_promotion_without_a_named_human_is_refused() -> None:
    decision = decide(result(0.61), result(0.55), look_recorded=True, approved_by=None)
    assert decision.promote is False
    assert "human" in decision.refusals


def test_every_failing_gate_is_reported_rather_than_the_first_one() -> None:
    """A gate that short-circuits sends a researcher round the loop once per problem, and each
    loop is another look at the holdout."""
    decision = decide(
        result(0.40, HASH_A), result(0.55, HASH_B), look_recorded=False, approved_by=None
    )
    assert set(decision.refusals) >= {"provenance", "budget", "human"}
    assert len(decision.reasons) == len(decision.refusals)


def test_a_provenance_value_that_is_not_a_hash_is_refused_at_construction() -> None:
    """This repository consumes a hash minted elsewhere. A local substitute is not one."""
    with pytest.raises(ValueError, match="not a SHA-256"):
        Result(
            model="m",
            version=1,
            score=0.5,
            provenance_sha256="unknown",
            configuration_hash="c" * 64,
        )


def test_a_decision_carries_a_reason_for_every_refusal() -> None:
    assert Decision(promote=False, refusals=("worse",)).reasons == (
        "the challenger did not beat the incumbent",
    )
