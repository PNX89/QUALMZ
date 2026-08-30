"""The facts the portfolio card states, checked against the repository rather than the file.

`docs/evidence/facts.json` is the one captured artefact CI does not compare byte for byte,
because it carries a capture date and a byte comparison of a date fails on the second morning.
That exemption is only defensible if its contents are checked another way.

AND THE CARD IS CHECKED AGAINST IT, which for a while nothing did. facts.json was held against
the repository here, the card was written from facts.json somewhere else, and the only thing
joining the two was an assertion that the FIRST line of the captured demo appeared in the HTML.
That line is a static header carrying no measured outcome, so every figure on the published page
was free: the test total, the release, the Python range, the capture date and every row of the
transcript could each be rewritten with the whole suite green, and were, one at a time.

The three exhibits are the card, the animation at the top of the README, and the transcript they
both show. All three are generated outside this repository, which is the reason the checks belong
inside it.
"""

from __future__ import annotations

import html as html_module
import json
import pathlib
import re
import subprocess
import sys
import tomllib
from typing import Any

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
FACTS = REPO / "docs" / "evidence" / "facts.json"
CARD = REPO / "site" / "index.html"
HERO = REPO / "docs" / "demo.svg"
DEMO = REPO / "docs" / "evidence" / "demo.txt"


def facts() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FACTS.read_text(encoding="utf-8"))
    return loaded


def captured() -> list[str]:
    """The demo's stdout, which CI re-runs and diffs, so it is the live run these are pinned to."""
    lines = DEMO.read_text(encoding="utf-8").splitlines()
    assert lines, "the captured demo is empty, so pinning anything to it checks nothing"
    return lines


def test_the_stated_test_total_counts_both_suites() -> None:
    """A total counting only `tests` would miss every test that needs a real PostgreSQL.

    The suites are split so that cloning and running pytest works with the dev group alone. That
    is an implementation detail of the rig, not of the repository, so the number a reader is
    shown covers both.
    """
    total = 0
    for directory in ("tests", "tests_store"):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", directory],
            capture_output=True,
            text=True,
            cwd=REPO,
            check=True,
        )
        total += sum(
            int(count) for _, count in re.findall(r"^(\S+): (\d+)$", result.stdout, re.MULTILINE)
        )
    assert total > 0
    assert facts()["tests"] == total, (
        f"the card states {facts()['tests']} tests and the two suites collect {total}. Re-run "
        f"scripts/capture_evidence.py"
    )


def test_the_stated_python_range_is_the_one_ci_runs() -> None:
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    versions = re.findall(r'"(\d+\.\d+)"', workflow)
    assert versions
    assert facts()["python"] == f"{min(versions, key=float)} to {max(versions, key=float)}"


def test_the_stated_release_matches_the_package_version() -> None:
    version = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    assert facts()["release"].startswith(f"v{version}")


def a_repository_whose_tag_was_left_behind(root: pathlib.Path) -> None:
    """A tree with a tag on a commit its HEAD is not descended from, which is the real shape.

    Built rather than described, because what is being tested is what git answers, and a fake
    that returned a list would be this test agreeing with itself.
    """
    # The identity and the signing setting are passed in rather than inherited, so this builds
    # the same repository on a machine that signs its commits as on a runner with no git config.
    git = [
        "git",
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "-c",
        "commit.gpgsign=false",
    ]
    (root / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    for command in (
        ["init", "-b", "main"],
        ["add", "-A"],
        ["commit", "-m", "the tree a reader sees"],
        ["commit", "--allow-empty", "-m", "the commit that was tagged"],
        ["tag", "v0.1.0"],
        ["reset", "--hard", "HEAD~1"],
    ):
        subprocess.run(git + command, cwd=root, check=True, capture_output=True)


def test_a_release_that_does_not_describe_this_tree_is_said_out_loud(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE NAME ON THE CARD WAS NEVER CHECKED AGAINST WHERE THE TAG POINTS.

    release() took the newest tag by version sort and returned it if it matched pyproject, which
    says nothing about the tree behind it. v0.1.0 in this repository is a tag on a branch main
    was rewritten away from, so the card's release link leads somewhere a reader would not
    recognise, and `git describe --tags HEAD` says no tag can describe this commit at all.

    DRIVEN THROUGH THE REAL FUNCTION ON A REAL REPOSITORY, for the reason the range check one
    file down gives: this repository's own state makes the check fire today, so a test asserting
    the current output would pass just as well with the check deleted.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    import capture_evidence

    a_repository_whose_tag_was_left_behind(tmp_path)
    monkeypatch.setattr(capture_evidence, "ROOT", tmp_path)

    assert capture_evidence.tags_describing_head() == set(), (
        "a tag on a commit this one is not descended from was counted as describing it"
    )
    assert capture_evidence.release() == "v0.1.0", (
        "the release name changed shape. The generator writes it into an href, so anything with "
        "a space in it is published as a broken link"
    )
    warned = capsys.readouterr().err
    assert "does not describe this commit" in warned, (
        "a tag that describes a different tree was published as this one's release with nothing "
        "said about it"
    )
    assert "git tag -f v0.1.0 HEAD" in warned, "the warning does not say how to put it right"


def test_the_capture_date_is_not_in_the_future() -> None:
    """Bounded rather than matched, because checking it against today fails tomorrow."""
    import datetime

    assert datetime.date.fromisoformat(facts()["captured"]) <= datetime.date.today()


def test_a_published_card_carries_no_banned_dash() -> None:
    """Only once one exists. A card is written at publication."""
    if not CARD.exists():
        return
    html = CARD.read_text(encoding="utf-8")
    # ESCAPES RATHER THAN THE CHARACTERS, and the first draft of this line used the characters
    # in the comment directly under a comment saying not to. The linter caught it.
    for dash in ("\u2014", "\u2013"):
        assert dash not in html, f"the published card contains {dash!r}"


def test_the_card_shows_the_captured_transcript_line_for_line() -> None:
    """THE WHOLE BLOCK, and it used to be the first line of it.

    The card says of this block: "It is committed to the repository and a test fails when it
    stops matching a live run, so this page cannot quietly drift from the code it describes."
    What failed was an assertion that the first non-blank line appeared somewhere in the HTML,
    and that line is "momentum has 3 looks at the 2024H2 holdout.", a header printed from a
    constant with no measured outcome in it. Every row beneath it, which is the entire argument
    the card is published to make, was unchecked: one row rewritten to say a crash bought a
    second look left the suite green and the publication gate passing.
    """
    if not CARD.exists():
        return
    blocks = re.findall(r"<pre[^>]*>(.*?)</pre>", CARD.read_text(encoding="utf-8"), re.S)
    assert len(blocks) == 1, (
        f"the card carries {len(blocks)} terminal blocks and this expects the one holding the "
        f"captured demo, so either the card gained a block or this is reading the wrong file"
    )
    shown = html_module.unescape(blocks[0]).splitlines()
    assert shown == captured(), (
        "the card's terminal block is not the captured output any more. CI re-runs the demo and "
        "diffs docs/evidence/demo.txt, so the card is the half of that chain that had drifted"
    )


def test_every_figure_on_the_card_is_the_captured_one() -> None:
    """EACH FIGURE READ OUT OF THE SENTENCE THAT CARRIES IT, not searched for on the page.

    The four facts on the card are literals in HTML written outside this repository. Nothing
    compared them to anything: the test total became 4200, the release v9.9.9, the capture date
    2030-01-01 and the Python range 2.7 to 4.0, one at a time, with the suite green each time.
    """
    if not CARD.exists():
        return
    html = CARD.read_text(encoding="utf-8")
    stated = {}
    for label in ("Tests", "Python", "Release"):
        found = re.search(rf"<dt>\s*{label}\s*</dt>\s*<dd>\s*([^<]+?)\s*</dd>", html)
        assert found, f"the card no longer states a {label} figure at all"
        stated[label] = found.group(1)

    note = re.search(r"Output captured on (\d{4}-\d{2}-\d{2})", html)
    assert note, "the card no longer says when its output was captured"

    against = facts()
    assert stated["Tests"] == str(against["tests"])
    assert stated["Python"] == against["python"]
    assert stated["Release"] == against["release"]
    assert note.group(1) == against["captured"], (
        f"the card says its output was captured on {note.group(1)} and the capture recorded "
        f"{against['captured']}. Re-run scripts/capture_evidence.py and rebuild the card"
    )

    # A SPACE IN AN ADDRESS IS A BROKEN LINK, and one was published: the release cell is written
    # into the release href, so at the tagged commit, where the capture read "v0.1.0 (untagged)",
    # the card linked to a URL with a bracket and a space in it. The inline favicon is a data URI
    # and is allowed its spaces, which is why this is scoped to the links a reader can follow.
    spaced = re.findall(r'href="https?://[^"]* [^"]*"', html)
    assert spaced == [], f"the card links to addresses with a space in them: {spaced}"


def test_the_animation_at_the_top_of_the_readme_shows_the_same_capture() -> None:
    """THE FIRST THING A READER SEES, and no test or CI step referred to it at all.

    docs/demo.svg is the hero of the README and is drawn from the same capture, so the same row
    rewritten there was a falsehood at the very top of the page with nothing anywhere to catch
    it. The long refusal line is clipped to the frame width by whatever draws this, so a clipped
    line is checked as a prefix rather than demanded in full.
    """
    nodes = [
        html_module.unescape(node)
        for node in re.findall(r"<text[^>]*>(.*?)</text>", HERO.read_text(encoding="utf-8"), re.S)
    ]
    assert nodes, "the animation draws no text at all"
    assert nodes[0].strip() == "$ uv run python examples/the_second_look.py", (
        "the animation names a different command from the one the capture was taken from"
    )

    drawn = nodes[2:]
    assert len(drawn) == len(captured()), (
        f"the animation draws {len(drawn)} lines of output and the capture has "
        f"{len(captured())}, so one of them is showing a run the other did not"
    )
    for line, real in zip(drawn, captured(), strict=True):
        if line.endswith("..."):
            assert real.startswith(line[: -len("...")]), (
                f"the animation shows {line!r}, which does not begin the captured line {real!r}"
            )
        else:
            assert line == real, f"the animation shows {line!r} and the capture says {real!r}"


def test_the_python_range_is_the_gating_matrix_and_orders_as_versions(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two latent defects in the function that publishes this number, neither of them visible.

    The range on the card is correct today. It was produced by a function that matched every
    quoted `x.y` anywhere in the workflow, so a quoted action version or a timeout would have
    landed on a published page, and that ordered with `float`, so `float("3.9") > float("3.13")`
    and a 3.9 leg would have published a range running backwards.

    A correct output from a broken mechanism is the thing this whole portfolio argues against, so
    the mechanism is tested rather than the output.
    """
    import json as _json
    import sys

    import yaml

    sys.path.insert(0, str(REPO / "scripts"))
    import capture_evidence

    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    gating: set[str] = set()
    for job in (workflow.get("jobs") or {}).values():
        if job.get("continue-on-error"):
            continue
        declared = (job.get("with") or {}).get("python-versions")
        if declared is None:
            continue
        gating.update(
            str(v) for v in (_json.loads(declared) if isinstance(declared, str) else declared)
        )

    assert gating, "no job gates on a Python version, so the published range verifies nothing"
    order = sorted(gating, key=lambda v: tuple(int(p) for p in v.split(".")))
    expected = f"{order[0]} to {order[-1]}"

    assert capture_evidence.python_range() == expected
    facts = _json.loads((REPO / "docs" / "evidence" / "facts.json").read_text("utf-8"))
    assert facts["python"] == expected, (
        f"the card says {facts['python']} and CI gates on {expected}"
    )

    # THE ORDERING RULE, DRIVEN THROUGH THE REAL FUNCTION rather than restated beside it.
    #
    # This matters because of how the defect hides. No matrix in this repository contains a 3.9,
    # so float ordering and version ordering agree on every version actually present, and
    # swapping the production line back to `key=float` changes no output and fails nothing. A
    # test that only asserted the rule as arithmetic would pin a fact and let the code revert.
    #
    # So the function is pointed at a workflow that DOES contain a 3.9, by moving its ROOT, and
    # asked what it returns. Under `key=float` that is "3.11 to 3.9", a range running backwards
    # on a published page.
    fake = tmp_path / ".github" / "workflows"
    fake.mkdir(parents=True)
    (fake / "ci.yml").write_text(
        'jobs:\n  checks:\n    with:\n      python-versions: \'["3.11", "3.9", "3.13"]\'\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(capture_evidence, "ROOT", tmp_path)
    assert capture_evidence.python_range() == "3.9 to 3.13", (
        "the version range is not ordered as versions. float('3.9') is greater than "
        "float('3.13'), so this publishes a range running backwards the day a 3.9 leg exists"
    )
