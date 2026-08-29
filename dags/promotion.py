"""The promotion, as control flow with a designed halt in the middle of it.

    airflow dags test promotion

WHY A DAG AT ALL, given that everything it calls is a function this repository already exposes.
Because the interesting property is not the order the steps run in, it is what happens when one
fails. A script that logs a warning and carries on and a script that stops are the same code
until the day something is wrong.

    EVERY GATE IS A SHORT CIRCUIT, not an assertion inside a task. A short circuit marks the
    tasks after it as skipped rather than failed, which is the right shape: a promotion that did
    not happen because the challenger lost is not an incident, and a pipeline that pages
    somebody for it is a pipeline whose alerts get muted.

    THE HALT IS A TASK, not a comment in a runbook. `awaiting_a_named_human` short-circuits
    unless an approval has been recorded. Nothing downstream of it runs, and the run is not
    marked failed: it is marked as having stopped where it was designed to stop.

WHAT THIS IS NOT. It is not Airflow in production and this repository does not claim to have run
it there. The configuration it is developed against is SQLite, and Airflow's own documentation
says of that: "There are plenty of limitations of using the SQLite database which you can easily
find online, and it should NEVER be used for production."
"""

from __future__ import annotations

import datetime
import os
import pathlib
import sys

from airflow.providers.standard.operators.python import PythonOperator, ShortCircuitOperator
from airflow.sdk import DAG

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from qualmz.gates import golden_digest, model_correctness

#: Who has approved this promotion, if anybody. Read from the environment rather than from a
#: constant so that the halt can be observed both ways in one test run.
APPROVED_BY = "QUALMZ_APPROVED_BY"


def _feature_frame_validates() -> bool:
    """Layer one. The real validation runs in the harness; the DAG's job is to stop on it."""
    return os.environ.get("QUALMZ_FRAME_VALID", "1") == "1"


def _model_is_unchanged() -> bool:
    import json

    pinned = json.loads(
        (
            pathlib.Path(__file__).resolve().parents[1]
            / "src"
            / "qualmz"
            / "data"
            / "golden_predictions.json"
        ).read_text(encoding="utf-8")
    )
    predictions = [
        float(value) for value in os.environ.get("QUALMZ_PREDICTIONS", "").split(",") if value
    ]
    if not predictions:
        return True
    return model_correctness(predictions, expected_digest=str(pinned["digest"])).passed


def _a_named_human_has_approved() -> bool:
    """THE DESIGNED HALT. Not a warning, not a timeout, and not a default of yes."""
    return bool(os.environ.get(APPROVED_BY, "").strip())


def _move_the_alias() -> str:
    return "the champion alias would move here"


with DAG(
    dag_id="promotion",
    description="Gate a challenger, then stop for a named human before anything is promoted",
    start_date=datetime.datetime(2026, 1, 1),
    schedule=None,  # No schedule anywhere in this repository. A promotion is triggered, not timed.
    catchup=False,
    tags=["promotion"],
) as dag:
    data_validation = ShortCircuitOperator(
        task_id="the_feature_frame_validates",
        python_callable=_feature_frame_validates,
    )
    correctness = ShortCircuitOperator(
        task_id="the_model_predicts_what_it_predicted",
        python_callable=_model_is_unchanged,
    )
    approval = ShortCircuitOperator(
        task_id="awaiting_a_named_human",
        python_callable=_a_named_human_has_approved,
    )
    promote = PythonOperator(
        task_id="move_the_champion_alias",
        python_callable=_move_the_alias,
    )

    data_validation >> correctness >> approval >> promote

__all__ = ["dag", "golden_digest"]
