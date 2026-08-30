"""The checks that exist because a sibling repository shipped without them.

Each one here is a defect that reached main somewhere else in this toolset and was found late.
They are cheap, they run before any of this repository's own subject matter exists, and they are
written first for that reason.
"""

from __future__ import annotations

import pathlib
import tomllib

REPO = pathlib.Path(__file__).resolve().parents[1]


def pyproject() -> dict[str, object]:
    loaded: dict[str, object] = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))
    return loaded


def test_the_package_imports_and_declares_a_version() -> None:
    """The cheapest possible check that the wheel layout is right."""
    import qualmz

    assert qualmz.__version__
    project = pyproject()["project"]
    assert isinstance(project, dict)
    assert qualmz.__version__ == project["version"], (
        "the package and pyproject state different versions, so the release tag would name one "
        "of them and the installed artefact the other"
    )


def test_every_declared_marker_is_carried_by_a_test() -> None:
    """A marker naming a rig that does not exist reads as coverage.

    A sibling declared three markers, two of which matched no test anywhere, and they were
    deselected by default so nothing ever ran them or reported their absence. The test guarding
    the list compared the three NAMES against pyproject, which is a check that the file agrees
    with itself.

    THIS REPOSITORY DECLARES NO MARKERS AT ALL, so the loop below runs zero times and asserts
    nothing today. It is left in as a tripwire for the day a marker is added here, rather than
    removed, because that is the one moment this exact defect could be introduced again.
    """
    tool = pyproject().get("tool", {})
    assert isinstance(tool, dict)
    pytest_config = tool.get("pytest", {})
    assert isinstance(pytest_config, dict)
    options = pytest_config.get("ini_options", {})
    assert isinstance(options, dict)
    declared = options.get("markers", [])
    assert isinstance(declared, list)

    body = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((REPO / "tests").glob("test_*.py"))
    )
    for marker in declared:
        name = str(marker).split(":")[0].strip()
        assert f"@pytest.mark.{name}" in body, (
            f"marker {name!r} is declared and no test carries it, so it describes a rig that "
            f"does not exist"
        )


def test_mypy_covers_every_directory_holding_python() -> None:
    """The list grows with the first file in a directory, and this is what fires on that commit.

    In a sibling, `scripts` was outside the mypy list, so the two scripts CI depended on were
    the only Python in the tree that nothing type checked. The list cannot simply be written in
    advance instead, because naming a directory mypy cannot find is an error rather than a no-op.
    """
    tool = pyproject()["tool"]
    assert isinstance(tool, dict)
    mypy = tool["mypy"]
    assert isinstance(mypy, dict)
    files = mypy["files"]
    assert isinstance(files, list)
    checked = {str(entry) for entry in files}

    holding = {
        path.relative_to(REPO).parts[0]
        for path in REPO.rglob("*.py")
        if ".venv" not in path.parts
        and "__pycache__" not in path.parts
        and len(path.relative_to(REPO).parts) > 1
    }
    missing = holding - checked
    assert missing == set(), f"these directories hold Python and mypy does not read them: {missing}"


def test_the_suite_that_needs_a_real_database_is_run_by_ci() -> None:
    """The other half of splitting the suite, and the half that is easy to forget.

    The offline suite runs the budget's rules against SQLite. The claim that the same schema and
    the same grant behave that way in PostgreSQL needs a PostgreSQL, so those tests live in
    their own directory, which makes them trivially skippable. The workflow is parsed and the
    command is asserted rather than the directory merely existing.
    """
    import yaml

    workflow = yaml.safe_load(
        (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    executed = "\n".join(
        line
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
        for line in step["run"].splitlines()
        if not line.strip().startswith("#")
    )
    assert (REPO / "tests_store").is_dir()
    collected = sorted(path.name for path in (REPO / "tests_store").glob("test_*.py"))
    assert collected, "tests_verdict is empty, so the split bought nothing"
    assert "pytest tests_store" in executed, (
        f"CI never runs tests_store, so {collected} are collected by nobody and the split "
        f"turned a slow suite into an unrun one"
    )


def test_no_third_party_binary_is_tracked() -> None:
    """A vendored engine binary in git history is a hundred megabytes nobody can remove later.

    ASKS GIT, AND THE FIRST VERSION WALKED THE WORKING TREE. It said "tracked" in its name and
    scanned every file on disk, so it went red the moment `.venv` contained a `soda` executable:
    a virtualenv is not the repository, and a test that cannot tell the difference reports a
    defect that does not exist while proving nothing about what was committed.
    """
    import subprocess

    listed = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=REPO, check=True
    ).stdout.split()
    names = {pathlib.PurePosixPath(entry).name for entry in listed}
    for binary in ("clickhouse", "duckdb_cli", "airflow"):
        assert binary not in names, f"a {binary} binary is committed"

    big = [
        entry
        for entry in listed
        if (REPO / entry).exists() and (REPO / entry).stat().st_size > 5_000_000
    ]
    assert big == [], f"these committed files are over five megabytes: {big}"


def test_the_offline_suite_imports_nothing_from_the_verdict_or_contract_groups() -> None:
    """The claim that cloning this and running pytest with `--dev` alone works.

    scikit-learn, DuckDB, Hypothesis and Soda are what the verdict is COMPUTED with, and they
    are named in their own dependency groups so that the boundary is visible in one file. The
    boundary only means anything if the offline suite really does stay on the other side of it,
    so it is asserted rather than intended, from the first commit rather than after the first
    time somebody notices.
    """
    # Hypothesis is deliberately NOT in this list. It is a test tool that ships in the dev
    # group beside pytest, and it computes no part of the verdict. Everything here is something
    # the verdict is measured WITH, which is the line the dependency groups draw.
    heavy = ("sklearn", "duckdb", "numpy", "soda")
    offenders: list[str] = []
    for path in sorted((REPO / "tests").glob("test_*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for package in heavy:
                if stripped.startswith((f"import {package}", f"from {package}")):
                    offenders.append(f"{path.name}: {stripped}")
    assert offenders == [], (
        f"the offline suite imports a measuring instrument, so it is no longer the thing a "
        f"stranger gets by cloning and running pytest: {offenders}"
    )


def test_mypy_passes_with_the_dev_group_alone() -> None:
    """The condition CI actually runs in, asserted rather than reasoned about.

    The lint job installs `--dev` and nothing else, so on a clean runner Great Expectations,
    MLflow and Airflow do not exist at all. That is a DIFFERENT mypy error from the one seen on
    a developer's machine, where they are installed but ship no types: `import-not-found` rather
    than `attr-defined`, and an override naming only the submodule silences the second and not
    the first. This repository shipped that exact mistake once.

    Rather than run mypy twice here, which would be slow and would need a second environment,
    the override list is checked to name each package at BOTH levels.
    """
    overrides = pyproject()["tool"]["mypy"]["overrides"]  # type: ignore[index]
    named: set[str] = set()
    for override in overrides:
        named.update(override.get("module", []))
    for package in ("great_expectations", "mlflow", "airflow"):
        assert package in named, (
            f"{package} is not named as an untyped module, so mypy will fail to find it on a "
            f"runner that installed the dev group alone"
        )
        assert f"{package}.*" in named, (
            f"{package}.* is not named, so a submodule import would fail even though the "
            f"package itself is declared"
        )
