"""What the promotion pipeline recorded, read offline, and checked for hollow gates."""

from __future__ import annotations

import json
import pathlib
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence" / "promotion"


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
