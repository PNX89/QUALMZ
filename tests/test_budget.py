"""The look budget, against SQLite, which speaks the same dialect the grant is enforced in.

What these defend is the difference between a budget and a suggestion: that a repeat costs
nothing, that a changed parameter costs one, that the store rather than the application is what
refuses, and that an ungranted budget is zero rather than unlimited.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from qualmz.budget import (
    SCHEMA_SQL,
    BudgetExhaustedError,
    Look,
    configuration_hash,
    looks_taken,
    take,
)


@pytest.fixture
def store() -> Iterator[sqlite3.Connection]:
    """CLOSED ON THE WAY OUT, and the first version of this returned without closing.

    `filterwarnings = ["error"]` turned the resulting ResourceWarning into a failure, which is
    the setting earning its place: an unclosed handle in a test fixture is the kind of thing
    that is invisible until a suite runs long enough to exhaust something.
    """
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("insert into look_budget values ('momentum', '2024H2', 3, '2026-08-29')")
        yield connection
    finally:
        connection.close()


def look(store_hash: str, result: str = "auc 0.51") -> Look:
    return Look("momentum", "2024H2", store_hash, "2026-08-29", result)


def test_a_repeat_of_the_same_configuration_does_not_cost_a_look(
    store: sqlite3.Connection,
) -> None:
    """The claim the first screenful makes, and the one worth attacking hardest."""
    digest = configuration_hash({"lookback": 20, "threshold": 0.5})
    assert take(store, look(digest)) is True
    assert looks_taken(store, "momentum", "2024H2") == 1

    for _ in range(10):
        assert take(store, look(digest)) is False
    assert looks_taken(store, "momentum", "2024H2") == 1, (
        "re-running an identical configuration moved the count, so the budget is a counter and "
        "a researcher can rewind it by rerunning a cell"
    )


def test_a_changed_parameter_is_a_new_look_and_costs_one(store: sqlite3.Connection) -> None:
    """The other half. A budget that charges nothing for a change is not a budget."""
    assert take(store, look(configuration_hash({"lookback": 20}))) is True
    assert take(store, look(configuration_hash({"lookback": 21}))) is True
    assert looks_taken(store, "momentum", "2024H2") == 2


def test_the_order_the_configuration_was_built_in_does_not_buy_a_look() -> None:
    """The loophole a hash over an unsorted payload would leave open."""
    assert configuration_hash({"a": 1, "b": 2}) == configuration_hash({"b": 2, "a": 1})


def test_a_value_json_cannot_write_down_is_refused_rather_than_stringified() -> None:
    """THE STABILITY THE DOCSTRING PROMISES, and the keyword that broke it both ways.

    `default=str` hashed the text of anything json could not represent, which is the opposite of
    stable. The same configuration holding a set of four feature names hashed three different
    ways in five fresh processes, because a set's text follows per-process string hash
    randomisation, so rerunning the same cell after a crash bought a fresh look every time. In
    the other direction a long array's text elides its middle, so two different parameter
    vectors hashed identically and a changed parameter cost nothing. Both halves of the claim
    this file opens with were false for the same reason.
    """
    for unwritable in ({"features": {"rsi", "macd"}}, {"weights": object()}):
        with pytest.raises(ValueError, match="json cannot represent"):
            configuration_hash(unwritable)


def test_the_digest_of_a_written_down_configuration_has_not_moved() -> None:
    """A ledger's identity cannot be improved quietly.

    Every look already recorded is a row carrying this value. Changing the canonical form makes
    all of them a NEW look and gives every researcher their budget back, so a change here is a
    migration rather than a tweak, and re-pinning this line is where that conversation starts.
    """
    assert configuration_hash({"lookback": 20, "threshold": 0.5}) == (
        "bedc554b06203bae18eb14f1d4a3803ae155cbe07c0fb4a90e5e3b2b00608b6f"
    )


def test_the_budget_refuses_the_look_after_the_last_one(store: sqlite3.Connection) -> None:
    for lookback in (10, 20, 30):
        assert take(store, look(configuration_hash({"lookback": lookback}))) is True
    with pytest.raises(BudgetExhaustedError, match="3 of 3 looks"):
        take(store, look(configuration_hash({"lookback": 40})))


class ASecondWorker:
    """A connection that lets another worker take a look the moment the count has been read.

    The race in one thread and with no timing in it. Every statement is run, its row is read,
    and only then is the rival let in, so the rival lands exactly in the gap between the read
    and the write. If there is no gap, it lands after a completed statement and finds the
    ledger as that statement left it.
    """

    def __init__(self, connection: sqlite3.Connection, rival: Look) -> None:
        self.connection = connection
        self.rival = rival
        self.let_in = False
        self.rival_was_refused = False

    def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> ASecondWorker:
        self.row = self.connection.execute(sql, parameters).fetchone()
        if "count(*) from look" in sql and not self.let_in:
            self.let_in = True
            try:
                take(self.connection, self.rival)
            except BudgetExhaustedError:
                self.rival_was_refused = True
        return self

    def fetchone(self) -> object:
        return self.row


def test_a_second_worker_between_the_count_and_the_write_cannot_overspend(
    store: sqlite3.Connection,
) -> None:
    """THE BUDGET IS SPENT BY THE STORE, and it used to be spent by three lines of Python.

    take() read the count, compared it against the grant, and inserted, with nothing of the
    store's holding across the three. Two workers evaluating two DIFFERENT configurations both
    passed the comparison and both inserted, and a budget of three recorded four looks with
    nothing raised. That is the application-code counter the module docstring argues against,
    which is what made this worth attacking rather than a race worth tolerating.

    The count and the write are one statement now, so there is no gap for the rival to land in.
    """
    for lookback in (10, 20):
        take(store, look(configuration_hash({"lookback": lookback})))

    racing = ASecondWorker(store, look(configuration_hash({"lookback": 99}), "the rival"))
    take(racing, look(configuration_hash({"lookback": 30})))

    assert racing.let_in, "the rival never ran, so this test watched nothing race anything"
    assert looks_taken(store, "momentum", "2024H2") == 3, (
        "two workers took a look each against a budget with one left in it, so the count is a "
        "number this repository holds rather than one the store does"
    )
    assert racing.rival_was_refused


def test_a_repeat_still_works_after_the_budget_is_exhausted(store: sqlite3.Connection) -> None:
    """A crash on the last look must not lock a researcher out of their own result."""
    digests = [configuration_hash({"lookback": n}) for n in (10, 20, 30)]
    for digest in digests:
        take(store, look(digest))
    assert take(store, look(digests[0])) is False, (
        "re-running an already recorded configuration was refused because the budget is spent, "
        "which punishes a crash and teaches people to work around the ledger"
    )


def test_a_second_window_is_a_second_budget_with_a_count_of_its_own(
    store: sqlite3.Connection,
) -> None:
    """THE WINDOW IS A THIRD OF THE KEY THE FIRST SENTENCE ADVERTISES, and nothing used two.

    Every fixture in both suites granted and spent against 2024H2 alone, so the window could be
    dropped from the primary key, or ignored by the count, or ignored by the lookup that decides
    whether a configuration has been seen, and the whole suite stayed green. All three were run
    as mutants and all three passed.

    What that costs in use is not cosmetic. With the window out of the key, a configuration
    evaluated against 2023H1 reads as already seen for 2024H2, so a fresh holdout hands back a
    stale verdict and the count does not move.
    """
    store.execute("insert into look_budget values ('momentum', '2023H1', 1, '2026-08-29')")
    digest = configuration_hash({"lookback": 20})
    earlier = Look("momentum", "2023H1", digest, "2026-08-29", "auc 0.49")

    assert take(store, earlier) is True
    assert looks_taken(store, "momentum", "2023H1") == 1
    assert looks_taken(store, "momentum", "2024H2") == 0, (
        "spending a look at 2023H1 moved 2024H2's count, so the two windows share one budget"
    )

    assert take(store, look(digest)) is True, (
        "the same configuration against a different window was treated as already seen, so a "
        "fresh holdout would hand back the verdict from the old one"
    )
    assert looks_taken(store, "momentum", "2024H2") == 1
    assert looks_taken(store, "momentum", "2023H1") == 1

    # 2024H2 KEEPS ITS WHOLE BUDGET. Counting across windows leaves the assertions above intact
    # and shows up only here, where the second window is asked for the rest of what it was
    # granted and a shared count has already spent one of them on the other window.
    for lookback in (40, 60):
        assert take(store, look(configuration_hash({"lookback": lookback}))) is True
    assert looks_taken(store, "momentum", "2024H2") == 3

    with pytest.raises(BudgetExhaustedError, match="1 of 1 looks"):
        take(store, Look("momentum", "2023H1", configuration_hash({"lookback": 40}), "d", "x"))


def test_an_ungranted_budget_is_zero_rather_than_unlimited(store: sqlite3.Connection) -> None:
    """The default that decides whether this is a control or a decoration."""
    with pytest.raises(BudgetExhaustedError, match="no budget has been granted"):
        take(store, Look("reversal", "2024H2", configuration_hash({"a": 1}), "2026-08-29", "x"))


def test_the_store_refuses_a_duplicate_even_if_the_application_does_not(
    store: sqlite3.Connection,
) -> None:
    """The constraint is in the schema, so a second path into the table cannot bypass it.

    This is what makes it a budget rather than a convention: an insert that goes around
    `take()` entirely still fails, which is the case every honour system loses.
    """
    digest = configuration_hash({"lookback": 20})
    take(store, look(digest))
    with pytest.raises(sqlite3.IntegrityError):
        store.execute(
            "insert into look values ('momentum', '2024H2', ?, '2026-08-30', 'smuggled')",
            (digest,),
        )


def test_an_empty_configuration_cannot_identify_a_look() -> None:
    """Otherwise every unconfigured run is the same look and the ledger records one forever."""
    with pytest.raises(ValueError, match="empty configuration"):
        configuration_hash({})
