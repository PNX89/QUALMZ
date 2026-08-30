"""What the promotion pipeline recorded, read offline, and checked for hollow gates."""

from __future__ import annotations

import ast
import json
import pathlib
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence" / "promotion"
HARNESS = REPO / "scripts" / "measure_promotion.py"


def summary() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    return loaded


def test_the_pipeline_promoted_once_and_refused_once() -> None:
    """A gate nobody has watched refuse is not a gate. One that never passes is not one either."""
    runs = summary()["runs"]
    assert runs["the same data version"]["promote"] is True
    assert runs["a different data version"]["promote"] is False
    assert "provenance" in runs["a different data version"]["refusals"]


def test_the_two_runs_differ_in_exactly_one_thing() -> None:
    """Otherwise the refusal could be explained by something other than the data version."""
    runs = summary()["runs"]
    assert runs["the same data version"]["refusals"] == []
    assert runs["a different data version"]["refusals"] == ["provenance"], (
        "the refused run failed more than the provenance gate, so it does not show that gate "
        "working on its own"
    )


def test_the_alias_moved_only_on_the_run_that_promoted() -> None:
    runs = summary()["runs"]
    assert runs["the same data version"]["alias_now_points_at_version"] == "2"
    assert runs["a different data version"]["alias_now_points_at_version"] is None


def resolved(tree: ast.Module, expression: ast.expr) -> str:
    """An expression as written, or the one expression a bare name was bound to."""
    if not isinstance(expression, ast.Name):
        return ast.unparse(expression)
    bound = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == expression.id
    ]
    assert len(bound) == 1, (
        f"{expression.id!r} is assigned {len(bound)} times, so it names no one thing"
    )
    return ast.unparse(bound[0])


def test_the_alias_move_and_the_recorded_verdict_cannot_disagree() -> None:
    """THE ACTION AND THE RECORD OF IT WERE TWO EXPRESSIONS, and the shorter one moved the alias.

    `decision.promote and validated` guarded the call, and
    `decision.promote and validated and all_passed(layers)` was written into the summary. Model
    correctness and performance, two of the four gates the README tabulates, were in the
    reported verdict and not in the guard on the action, so a run with the pinned golden digest
    changed printed that it had not promoted, exited 1, and had already set the champion alias
    in the registry.

    Read from the source rather than from the summary because the recorded run is the one where
    every layer passed, which is exactly the run that cannot tell the two conditions apart. The
    two expressions are required to be the same expression, whatever it is called.
    """
    tree = ast.parse(HARNESS.read_text(encoding="utf-8"))

    guards = [
        node.test
        for node in ast.walk(tree)
        if isinstance(node, ast.IfExp) and "move_the_alias(" in ast.unparse(node.body)
    ]
    assert len(guards) == 1, (
        f"{len(guards)} conditional alias moves were found in the harness, and this expects one. "
        f"Either the alias moved unconditionally or this test is reading the wrong file"
    )
    recorded = [
        value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant) and key.value == "promote"
    ]
    assert len(recorded) == 1, (
        f"{len(recorded)} promotion verdicts are recorded, and this expects one"
    )

    assert ast.unparse(guards[0]) == ast.unparse(recorded[0]), (
        f"the alias moves on {ast.unparse(guards[0])!r} and the run is recorded as "
        f"{ast.unparse(recorded[0])!r}. Two expressions is two decisions, and the one guarding "
        f"the action is the one that promotes"
    )

    verdict = resolved(tree, guards[0])
    for gate in ("decision.promote", "validated", "all_passed(layers)"):
        assert gate in verdict, (
            f"the alias moves on {verdict!r}, which does not consult {gate}. The README says "
            f"each of the four gates stops the promotion on its own"
        )


def test_the_golden_digest_is_read_from_a_committed_file_and_not_recomputed() -> None:
    """THE GATE THAT WAS HOLLOW FOR ONE COMMIT.

    The first version computed the pinned digest from the same predictions it then compared
    against, so it passed for any model at all: a value compared to itself. The digest now lives
    in a committed file, and this asserts the recorded run used that value.
    """
    pinned = json.loads(
        (REPO / "src" / "qualmz" / "data" / "golden_predictions.json").read_text(encoding="utf-8")
    )
    assert summary()["golden_digest"] == pinned["digest"], (
        "the recorded run used a digest that is not the committed one, so the golden set is "
        "being recomputed rather than checked"
    )
    assert len(pinned["digest"]) == 64
    assert pinned["predictions"] > 0

    harness = (REPO / "scripts" / "measure_promotion.py").read_text(encoding="utf-8")
    assert "pinned = str(json.loads(golden.read_text" in harness, (
        "the harness no longer reads the pinned digest from the committed file"
    )


def test_all_three_layers_ran_and_are_named() -> None:
    """A pipeline claiming three layers has to show three."""
    numbers = summary()
    assert numbers["data_validation"]["passed"] is True
    assert numbers["data_validation"]["failed_expectations"] == []
    layers = {entry["layer"] for entry in numbers["layers"]}
    assert layers == {"model correctness", "performance"}, (
        f"the layers recorded are {layers}, and data validation is recorded separately because "
        f"it runs before the model sees the frame"
    )
    for entry in numbers["layers"]:
        assert entry["passed"] is True
        assert entry["detail"].strip()


def test_the_transcript_names_the_one_value_that_differs() -> None:
    text = (EVIDENCE / "two-runs.txt").read_text(encoding="utf-8")
    assert "differ in more than the model" in text
    assert "REFUSED" in text and "PROMOTED" in text
