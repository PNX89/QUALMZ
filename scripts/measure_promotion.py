"""Run the promotion pipeline end to end, and record every gate's answer.

    uv run --group promotion python scripts/measure_promotion.py

WHAT IS MEASURED. A challenger arrives against a champion. Four things have to be true before
the alias moves, and each is recorded whether it passed or failed:

    1. the feature frame validates, checked by Great Expectations before the model sees it
    2. the model still predicts what it predicted, against a pinned golden set
    3. a batch still fits its wall-clock budget
    4. the challenger and the incumbent were scored on the SAME data version, and the hash that
       says so was minted where the dataset was admitted, not here

AND THE RUN IS DONE TWICE. Once where everything is in order and the alias moves, and once with
a challenger scored on a different data version, where it does not. A gate nobody has watched
refuse is not a gate, and the second run is what makes the first one worth printing.
"""

from __future__ import annotations

import csv
import json
import os
import pathlib
import sys
import tempfile
import warnings
from typing import Any

os.environ.setdefault("GX_ANALYTICS_ENABLED", "false")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qualmz.gates import all_passed, golden_digest, model_correctness, performance  # noqa: E402
from qualmz.promotion import Result, decide  # noqa: E402

OUT = ROOT / "docs" / "evidence" / "promotion"
DATA = ROOT / "src" / "qualmz" / "data"

#: The hash a sibling minted when it admitted the dataset. It is a value this repository is
#: HANDED. Nothing here can produce one, which is what the seam is worth.
ADMITTED_DATA_VERSION = "d8d37f0c60ad66504d1aa39badf79d8350456d8d2b62e337a36c59b51a323b63"
A_DIFFERENT_DATA_VERSION = "0" * 64

SECONDS_ALLOWED = 0.5


def feature_frame() -> Any:
    """The committed paired returns, as the frame a model would be scored on."""
    import pandas as pd

    with (DATA / "paired_returns.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return pd.DataFrame(
        {
            "day": [int(row["day"]) for row in rows],
            "simulated": [float(row["simulated"]) for row in rows],
            "live": [float(row["live_with_a_bug"]) for row in rows],
        }
    )


def validate(frame: Any) -> tuple[bool, list[str]]:
    """Layer one, run before the model sees anything."""
    import great_expectations as gx

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        context = gx.get_context(mode="ephemeral")
        source = context.data_sources.add_pandas("in_memory")
        asset = source.add_dataframe_asset(name="features")
        batch = asset.add_batch_definition_whole_dataframe("whole")
        suite = context.suites.add(gx.ExpectationSuite(name="feature_frame"))
        for expectation in (
            gx.expectations.ExpectColumnValuesToNotBeNull(column="simulated"),
            gx.expectations.ExpectColumnValuesToNotBeNull(column="live"),
            gx.expectations.ExpectColumnValuesToBeBetween(
                column="simulated", min_value=-0.5, max_value=0.5
            ),
            gx.expectations.ExpectTableRowCountToBeBetween(min_value=100, max_value=10_000),
        ):
            suite.add_expectation(expectation)
        definition = context.validation_definitions.add(
            gx.ValidationDefinition(data=batch, suite=suite, name="before_scoring")
        )
        outcome = definition.run(batch_parameters={"dataframe": frame})

    failures = [
        str(entry["expectation_config"]["type"])
        for entry in outcome["results"]
        if not entry["success"]
    ]
    return bool(outcome.success), failures


def predictions(frame: Any) -> list[float]:
    """A deliberately boring model, because the subject here is the pipeline, not the model."""
    return [round(float(value) * 100, 8) for value in frame["simulated"].tolist()[:50]]


def move_the_alias(challenger_version: int) -> str:
    """Set the champion alias in a real MLflow registry, on a temporary SQLite store.

    AN ALIAS, NOT A STAGE. Measured on MLflow 3.15.2: `transition_model_version_stage` still
    exists and still works, and warns that stages will be removed in a future major release. So
    this is a decision rather than a necessity, which is why it is written down.
    """
    import mlflow
    from mlflow import MlflowClient

    with tempfile.TemporaryDirectory() as directory:
        mlflow.set_tracking_uri(f"sqlite:///{directory}/registry.db")
        client = MlflowClient()
        client.create_registered_model("momentum")
        for _ in range(challenger_version):
            client.create_model_version("momentum", source=f"file://{directory}", run_id=None)
        client.set_registered_model_alias("momentum", "champion", str(challenger_version))
        found = client.get_model_version_by_alias("momentum", "champion")
        return str(found.version)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frame = feature_frame()

    validated, failures = validate(frame)
    scored = predictions(frame)

    # THE PINNED DIGEST IS READ FROM A COMMITTED FILE, and the first version of this computed it
    # from the same predictions it then checked. That gate passed on any model at all: it was
    # comparing a value to itself, which is the exact shape of defect this repository's own
    # tests are written to catch, one file away from the tests that catch it.
    golden = DATA / "golden_predictions.json"
    if not golden.exists():
        golden.write_text(
            json.dumps({"digest": golden_digest(scored), "predictions": len(scored)}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"pinned a new golden set in {golden.relative_to(ROOT)}", file=sys.stderr)
    pinned = str(json.loads(golden.read_text(encoding="utf-8"))["digest"])

    layers = [
        model_correctness(scored, expected_digest=pinned),
        performance(lambda: predictions(frame), seconds_allowed=SECONDS_ALLOWED),
    ]

    runs: dict[str, dict[str, Any]] = {}
    for name, challenger_version in (
        ("the same data version", ADMITTED_DATA_VERSION),
        ("a different data version", A_DIFFERENT_DATA_VERSION),
    ):
        challenger = Result("momentum", 2, 0.61, challenger_version, "c" * 64)
        incumbent = Result("momentum", 1, 0.55, ADMITTED_DATA_VERSION, "c" * 64)
        decision = decide(challenger, incumbent, look_recorded=True, approved_by="quelin")
        alias_moved_to = move_the_alias(2) if (decision.promote and validated) else None
        runs[name] = {
            "promote": decision.promote and validated and all_passed(layers),
            "refusals": list(decision.refusals),
            "reasons": list(decision.reasons),
            "alias_now_points_at_version": alias_moved_to,
        }

    summary: dict[str, Any] = {
        "data_validation": {"passed": validated, "failed_expectations": failures},
        "layers": [
            {"layer": layer.layer, "passed": layer.passed, "detail": layer.detail}
            for layer in layers
        ],
        "seconds_allowed": SECONDS_ALLOWED,
        "golden_digest": pinned,
        "runs": runs,
    }

    good = runs["the same data version"]
    bad = runs["a different data version"]
    if not good["promote"]:
        print(
            "the in-order run did not promote, so nothing here has been seen working",
            file=sys.stderr,
        )
        return 1
    if bad["promote"]:
        print("a challenger scored on a different data version was promoted", file=sys.stderr)
        return 1

    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    with (OUT / "two-runs.txt").open("w", encoding="utf-8") as handle:
        print("$ uv run --group promotion python scripts/measure_promotion.py", file=handle)
        print(file=handle)
        print("Three layers, run before anything is promoted:", file=handle)
        print(
            f"  data validation     {'passed' if validated else 'FAILED'}"
            f"   (Great Expectations, before the model sees the frame)",
            file=handle,
        )
        recorded_layers: list[dict[str, Any]] = summary["layers"]
        for layer in recorded_layers:
            print(
                f"  {layer['layer']:<20}{'passed' if layer['passed'] else 'FAILED'}   "
                f"{layer['detail']}",
                file=handle,
            )
        print(file=handle)
        print("Then the same promotion, twice:", file=handle)
        print(file=handle)
        for name, entry in runs.items():
            run: dict[str, Any] = entry
            outcome = "PROMOTED" if run["promote"] else "REFUSED"
            print(f"  {name:<26}{outcome}", file=handle)
            for reason in run["reasons"]:
                print(f"      {reason}", file=handle)
            if run["alias_now_points_at_version"]:
                print(
                    f"      the champion alias now points at version "
                    f"{run['alias_now_points_at_version']}",
                    file=handle,
                )
        print(file=handle)
        print(
            "The second run differs from the first in one value: the data version the challenger",
            file=handle,
        )
        print(
            "was scored on. Every number in it is correct and the comparison is between two",
            file=handle,
        )
        print("things that differ in more than the model.", file=handle)
    print((OUT / "two-runs.txt").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
