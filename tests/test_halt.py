"""The designed halt, checked against what Airflow itself printed.

The claim is not that the DAG exists. It is that a run with no approval STOPS before the alias
moves, that a run with one goes through, and that the stopped run is not reported as a failure.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence" / "halt"


def summary() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    return loaded


def test_a_run_without_an_approval_skips_what_comes_after_it() -> None:
    without = summary()["without_an_approval"]
    assert without["tasks_skipped"] >= 1, (
        "nothing was skipped when no approval was recorded, so the halt did not halt"
    )


def test_a_run_with_an_approval_skips_nothing() -> None:
    """The other direction. A halt that cannot be passed is a wall."""
    assert summary()["with_an_approval"]["tasks_skipped"] == 0


def test_the_halted_run_is_not_reported_as_a_failure() -> None:
    """A promotion waiting on a human is not an incident.

    This is the difference between a pipeline people read and one whose alerts get muted. A run
    that stops where it was designed to stop finishes successful.
    """
    assert summary()["without_an_approval"]["run_state"] == "success"


def test_every_gate_in_the_dag_is_a_short_circuit_rather_than_an_assertion() -> None:
    """An assertion inside a task marks the run FAILED, which is the wrong shape for a gate.

    Read from the source rather than by importing the DAG, so the offline suite stays runnable
    without Airflow installed.
    """
    source = (REPO / "dags" / "promotion.py").read_text(encoding="utf-8")
    assert source.count("ShortCircuitOperator(") == 3, (
        "the DAG no longer has three short-circuit gates, so at least one of them either "
        "asserts, which fails the run, or does not stop anything"
    )
    assert "schedule=None" in source, "the DAG carries a schedule, and a promotion is triggered"
    assert "PythonOperator(" in source


def test_the_dag_does_not_default_the_approval_to_yes() -> None:
    """The single most valuable line to read in a file like this."""
    source = (REPO / "dags" / "promotion.py").read_text(encoding="utf-8")
    assert 'os.environ.get(APPROVED_BY, "")' in source, (
        "the approval no longer defaults to absent, and a default of yes turns a designed halt "
        "into a comment"
    )


def test_the_repository_does_not_claim_airflow_in_production() -> None:
    """It is developed against SQLite, and the vendor's own words about that are quoted.

    WHITESPACE FLATTENED BEFORE COMPARING, which is not fussiness. Every sentence in this
    repository is wrapped at a hundred columns, so a search for a contiguous phrase fails the
    moment the phrase crosses a line, and it fails for a reason that has nothing to do with the
    claim being checked.
    """
    source = " ".join((REPO / "dags" / "promotion.py").read_text(encoding="utf-8").split())
    assert "NEVER be used for production" in source
    assert "does not claim to have run it there" in source
