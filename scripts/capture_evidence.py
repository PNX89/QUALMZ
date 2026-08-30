"""Capture what the portfolio card shows: the demo's stdout, and the facts beside it.

    uv run python scripts/capture_evidence.py

    docs/evidence/demo.txt    the demo's stdout, byte for byte, diffed by CI
    docs/evidence/facts.json  the test total, the Python range, the release and the capture date

facts.json is the one captured file CI does NOT compare byte for byte, because it carries a
capture date and a byte comparison of a date fails on the second morning. Its contents are held
by tests/test_card.py instead, which checks the claims rather than the timestamp.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "the_second_look.py"
EVIDENCE = ROOT / "docs" / "evidence"


def test_total() -> int:
    """Collected by pytest across BOTH suites, because the split is an implementation detail.

    A total that counted only `tests` would understate the repository by every test that needs
    a real PostgreSQL, which is where the grant is watched refusing.
    """
    total = 0
    for directory in ("tests", "tests_store"):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", directory],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=True,
        )
        per_file = re.findall(r"^(\S+): (\d+)$", result.stdout, re.MULTILINE)
        if not per_file:
            raise SystemExit(f"pytest collected nothing in {directory}:\n{result.stdout[-400:]}")
        on_disk = len(list((ROOT / directory).glob("test_*.py")))
        if len(per_file) != on_disk:
            raise SystemExit(
                f"pytest reported {len(per_file)} files in {directory} and {on_disk} exist"
            )
        total += sum(int(count) for _, count in per_file)
    return total


def python_range() -> str:
    """The versions CI will FAIL the build over, read as structure and ordered as versions.

    TWO DEFECTS, BOTH LATENT RATHER THAN LIVE. The published range is correct today and was
    produced by a function that cannot be relied on to keep it correct.

    First, it matched every quoted `x.y` anywhere in the workflow, not the Python matrix. A
    quoted action version or a timeout would have landed on the published card. This repository's
    sibling generator already carries the lesson, that a list has to be read as structure and
    never as text that looks like structure, and it had not been carried here.

    Second, and worse, it ordered with `float`. `float("3.9")` is 3.9 and `float("3.13")` is
    3.13, so the moment a 3.9 leg existed the card would have published a range running
    backwards. Versions are tuples of integers, not decimals.

    A job allowed to fail is also skipped now. An advisory leg is a good thing to run and a
    dishonest thing to advertise, which is the defect this same function had in QUOTEZ, where it
    published 3.14 support the build would not fail over.
    """
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    versions: set[str] = set()
    for job in (workflow.get("jobs") or {}).values():
        if job.get("continue-on-error"):
            continue
        declared = (job.get("with") or {}).get("python-versions")
        if declared is None:
            continue
        parsed = json.loads(declared) if isinstance(declared, str) else declared
        versions.update(str(v) for v in parsed)
    if not versions:
        raise SystemExit(
            "no gating job declares python-versions, so this card would state a range that "
            "nothing verifies"
        )
    ordered = sorted(versions, key=lambda v: tuple(int(part) for part in v.split(".")))
    return f"{ordered[0]} to {ordered[-1]}"


def tags_describing_head() -> set[str]:
    """The tags an ancestor of this commit carries, which is not the same as the tags that exist.

    `git tag` lists every tag in the repository, wherever it points. A tag cut on a branch that
    was later rewritten still lists, and the tree behind it is not the tree a reader is looking
    at.
    """
    listed = subprocess.run(
        ["git", "tag", "--merged", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=True
    )
    return set(listed.stdout.split())


def release() -> str:
    """The release the card names, and whether it describes the tree the card was built from.

    THE NAME WAS PUBLISHED WITHOUT BEING CHECKED. This took the newest tag by version sort and
    returned it if it matched pyproject, which says nothing about where the tag points. v0.1.0
    points at a commit that is not an ancestor of main, because the branch was rewritten after
    tagging, so the card's release link leads to a tree that is not the repository underneath it.

    IT SAYS SO RATHER THAN REFUSING, and refusing was the first instinct. The card is built from
    this file's output by a generator outside this repository, which writes the release string
    straight into an href, so the only other value that can be returned here reaches the page as
    an address with a space in it. A broken link on the published page is a worse defect than a
    stale one, and failing outright stops every capture and every CI run until somebody re-cuts a
    published tag, which is not a decision this script gets to force. Re-cutting the tag is the
    fix, and this is the sentence that says so out loud until it happens.
    """
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    tags = subprocess.run(
        ["git", "tag", "--sort=-v:refname"], capture_output=True, text=True, cwd=ROOT, check=True
    ).stdout.split()
    if not tags:
        return f"v{version} (untagged)"
    if tags[0] != f"v{version}":
        raise SystemExit(f"pyproject says {version} and the newest tag is {tags[0]}")
    if tags[0] not in tags_describing_head():
        print(
            f"{tags[0]} does not describe this commit: it is a tag on a branch this one was "
            f"rewritten away from, so the card's release link leads to a different tree. "
            f"Re-cut it with `git tag -f {tags[0]} HEAD` and push the tag before publishing",
            file=sys.stderr,
        )
    return tags[0]


def main() -> int:
    result = subprocess.run(
        [sys.executable, str(DEMO)], capture_output=True, text=True, cwd=ROOT, check=False
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    if not result.stdout.strip():
        print("the demo printed nothing, so there is no card to build", file=sys.stderr)
        return 1

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "demo.txt").write_text(result.stdout, encoding="utf-8")

    run_id = os.environ.get("GITHUB_RUN_ID")
    slug = os.environ.get("GITHUB_REPOSITORY", "PNX89/QUALMZ")
    facts = {
        "tests": test_total(),
        "python": python_range(),
        "release": release(),
        "captured": datetime.date.today().isoformat(),
        "runUrl": f"https://github.com/{slug}/actions/runs/{run_id}" if run_id else None,
    }
    (EVIDENCE / "facts.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    print(f"wrote docs/evidence/demo.txt ({len(result.stdout.splitlines())} lines)")
    print(f"wrote docs/evidence/facts.json {facts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
