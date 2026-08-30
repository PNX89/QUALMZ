"""Every checkable claim on the front page, checked, and written before the page existed.

Four kinds of claim, following the contract this toolset shares:

    NUMBER     a figure on the page against the measurement that produced it
    COMMAND    a command the page offers against what CI actually runs
    OUTPUT     a quoted block, line by line, against the transcript it names
    REFERENCE  every link and path against what exists

Plus the one this repository needs and the others do not: a VOCABULARY check. Every claim here
is bounded, and a page that says a rule prevents or eliminates anything has stopped describing
what was measured.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
README = (REPO / "README.md").read_text(encoding="utf-8")
EVIDENCE = REPO / "docs" / "evidence"


def evidence(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (EVIDENCE / name / "summary.json").read_text(encoding="utf-8")
    )
    return loaded


def own_prose() -> str:
    """The page minus the generated cross-link footer, which describes other repositories."""
    start, end = "<!-- toolset:start -->", "<!-- toolset:end -->"
    if start in README and end in README:
        return README[: README.index(start)] + README[README.index(end) + len(end) :]
    return README


def test_the_numbers_on_the_page_are_the_measured_ones() -> None:
    """NUMBER, as a table of claim against source, so an unedited neighbour is visible.

    EACH FIGURE IS LOOKED FOR IN THE SENTENCE THAT CARRIES IT, and the first version of this
    asked only whether the digits appeared anywhere on the page. Two things were wrong with
    that. `"500" in README` is satisfied by "5000", so a figure that drifts by gaining a digit
    passes, which was demonstrated: 500 days rewritten as 5000 and 25 blocks as 250 left the
    suite green. And a one-character figure is satisfied by any line at all, so the tasks-skipped
    claim was being met by "1 of 3 used" in the demo block and the alias version by "2 of 3
    used", neither of which is the sentence the claim is about.

    The pattern beside each value is the shortest phrase that identifies the sentence rather
    than the whole of it, because the page is allowed to be rewritten around its figures.
    """
    divergence = evidence("divergence")
    halt = evidence("halt")

    # TO TWO PLACES on the statistics, which is what the transcript prints and therefore what a
    # reader sees. The summary keeps three. Asserting the summary's precision would demand the
    # page quote a number its own exhibit does not show.
    claims = {
        "days in the paired series": (r"paired series of {}\s+days", str(divergence["days"])),
        "blocks": (
            r"across\s+{}\s+non-overlapping blocks",
            str(divergence["cases"]["bad luck"]["blocks"]),
        ),
        "the naive statistic on bad luck": (
            r"bad luck\s+\S+\s+{}\s",
            f"{divergence['cases']['bad luck']['naive_t']:.2f}",
        ),
        "the block statistic on bad luck": (
            r"non-overlapping blocks gives {}",
            f"{divergence['cases']['bad luck']['block_t']:.2f}",
        ),
        "the naive statistic on a bug": (
            r"a bug\s+\S+\s+{}\s",
            f"{divergence['cases']['a bug']['naive_t']:.2f}",
        ),
        "tasks skipped with no approval": (
            r"tasks_skipped={}\b",
            str(halt["without_an_approval"]["tasks_skipped"]),
        ),
        "the state a halted run finishes in": (
            r"state={}\b",
            str(halt["without_an_approval"]["run_state"]),
        ),
    }
    # THE ALIAS VERSION IS NOT IN THIS TABLE, and it was, matching the "2" in "2 of 3 used".
    # The page does not state which version the alias moved to, so there is no figure here to
    # check; the recorded one is held against the run that produced it in
    # tests/test_promotion_evidence.py instead.
    missing = {
        name: value
        for name, (pattern, value) in claims.items()
        if not re.search(pattern.format(re.escape(value)), README)
    }
    assert missing == {}, f"the README no longer states these measured figures: {missing}"


def test_the_page_states_the_refusal_the_gate_exists_for() -> None:
    """NUMBER and OUTPUT together: the refused run, with its reason."""
    refused = evidence("promotion")["runs"]["a different data version"]
    assert refused["promote"] is False
    assert "differ in more than the model" in README


#: Figures the page carries that are names rather than measurements, declared one at a time with
#: the reason. A regex wide enough to skip these by their shape would skip a stale figure too.
NOT_A_MEASUREMENT = {
    256: "SHA-256 is the name of an algorithm",
}


def visible_prose() -> str:
    """The page as a reader sees it: no link targets, and no cross-link footer.

    A URL is not a claim. The Python badge's target carries `%20`, and reading a figure out of an
    address nobody sees would either fail on a colour or teach whoever hit it to widen the
    exception list until the check stopped meaning anything.
    """
    without_targets = re.sub(r"\]\([^)]*\)", "]", own_prose())
    return re.sub(r"https?://\S+", "", without_targets)


def test_no_large_number_on_the_page_is_one_nothing_measured() -> None:
    """The half the table above cannot do: a stale copy of a figure elsewhere on the page.

    THE SCAN USED TO MATCH NOTHING AT ALL. It looked for `\\b\\d{1,3}(?:,\\d{3})+\\b`, which is
    a number written with thousands separators, and this page contains none, so `written` was
    the empty set on every run and the assertion below was a tautology. The probe that proved it
    is now the first assertion in the test: a scan with an empty field of view is not a check.

    Digits after a decimal point are not integers on the page, so -0.000284 is not read as
    284: the two-place statistics are held by name in the table above, where a change to one of
    them says which one.
    """
    divergence = evidence("divergence")
    measured: set[int] = {divergence["days"], divergence["seed"], divergence["drag_from_day"]}
    for case in divergence["cases"].values():
        measured.add(case["blocks"])
    written = {int(token) for token in re.findall(r"(?<![\d.])\d{3,}(?![\d])", visible_prose())}
    assert written, "the scan found no figure at all on the page, so it is checking nothing"
    invented = sorted(written - measured - set(NOT_A_MEASUREMENT))
    assert invented == [], (
        f"the page states {invented}, and nothing under docs/evidence produces those figures"
    )


def test_every_command_the_page_offers_is_one_ci_runs() -> None:
    """COMMAND. Except the three that run inside the shared workflow, which is named."""
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    executed = "\n".join(
        line
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
        for line in step["run"].splitlines()
        if not line.strip().startswith("#")
    )
    shared = "PNX89/.github/.github/workflows/checks.yml"
    assert shared in (REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    delegated = ("uv run pytest", "uv run ruff", "uv run mypy", "uv sync")

    offered = re.findall(r"^\s*(?:\$ )?(uv run [^\n]+|scripts/\S+)$", README, re.MULTILINE)
    assert offered, "the README offers no command at all"
    for command in offered:
        command = command.strip()
        if command.startswith(delegated):
            continue
        assert command in executed, f"the README offers `{command}` and CI never runs it"


def test_every_block_quoted_from_a_transcript_is_in_that_transcript() -> None:
    """OUTPUT, line by line, against the file each block names in an HTML comment."""
    blocks = re.findall(r"<!-- quoted from (\S+) -->\n```text\n(.*?)```", README, re.S)
    assert blocks, "no block on the page declares where it was quoted from"
    for path, body in blocks:
        source = REPO / path
        assert source.exists(), f"the page quotes {path}, which does not exist"
        lines = {line.strip() for line in source.read_text("utf-8").splitlines()}
        for line in body.splitlines():
            if line.strip():
                assert line.strip() in lines, (
                    f"the page quotes {line.strip()!r} as coming from {path}, and it is not there"
                )


def test_every_path_and_link_on_the_page_exists() -> None:
    """REFERENCE, including the paths written as inline code."""
    targets = set(re.findall(r"\]\((?!https?:)([^)#]+)", README))
    targets |= {
        found
        for found in re.findall(r"`([a-zA-Z0-9_./-]+)`", README)
        if "/" in found and not found.startswith(("http", "-"))
    }
    missing = sorted(target for target in targets if not (REPO / target.strip()).exists())
    assert missing == [], f"the README points at paths that do not exist: {missing}"


#: Phrases this repository must not CLAIM. Some belong to a sibling and some overclaim, and the
#: check below is about the claim rather than the word: a page saying it is NOT Airflow in
#: production is doing the right thing, and a blanket ban would fail it for saying so.
CLAIMS_TO_AVOID = (
    "unbreakable",
    "in production",
    "at scale",
    "live capital",
    "track record",
    "makes money",
)

#: Vocabulary belonging to a sibling repository. These are banned outright, negation or not,
#: because using a sibling's phrase even to disclaim it is still describing its subject.
BELONGS_TO_A_SIBLING = (
    "permutation",
    "empirical null",
    "minimum detectable effect",
    "embargo",
    "vendor contract",
    "admission verdict",
    "rejection ledger",
    "vintage",
    "property-based",
)

NEGATIONS = ("not ", "no ", "never ", "nothing ", "cannot ", "does not", "without ")


def sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", " ".join(text.split()))]


@pytest.mark.parametrize("phrase", CLAIMS_TO_AVOID)
def test_the_page_never_claims_what_it_cannot_support(phrase: str) -> None:
    """THE CHECK IS ON THE CLAIM, NOT THE WORD, and the first version was on the word.

    It failed on this repository's own disclaimers: "It is not Airflow in production", "does not
    allocate capital, hold a track record, or claim any strategy makes money". A ban that fires
    on the sentence saying no is a ban that pushes the disclaimer off the page, which is the
    opposite of what it is for.

    So every sentence containing one of these has to contain a negation as well.
    """
    for sentence in sentences(own_prose()):
        if phrase in sentence.lower():
            assert any(negation in sentence.lower() for negation in NEGATIONS), (
                f"this sentence claims {phrase!r} rather than denying it: {sentence!r}"
            )


@pytest.mark.parametrize("phrase", BELONGS_TO_A_SIBLING)
def test_the_page_does_not_use_a_siblings_vocabulary_at_all(phrase: str) -> None:
    """Banned outright: using a sibling phrase even to disclaim it describes its subject."""
    assert phrase not in own_prose().lower()


def test_the_page_says_what_it_adopted_rather_than_built() -> None:
    """The first screenful has to name the sibling whose schema and grant this uses.

    A repository that quietly reuses another's design and describes it as its own is the kind of
    thing that only shows up when somebody opens both. Saying it in the first screenful costs a
    sentence and is the reason this one is smaller than it looks.
    """
    first = " ".join(README.splitlines()[:45]).lower()
    assert "quizz" in first, "the first screenful does not name the repository this adopts from"
    assert "adopt" in first or "borrowed" in first


def test_the_page_says_no_capital_was_allocated() -> None:
    """The sentence that has to be there, not merely the absence of the ones that must not."""
    flattened = " ".join(own_prose().split()).lower()
    assert "no capital was ever allocated" in flattened
    assert "generated" in flattened
