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


def test_the_budget_refuses_the_look_after_the_last_one(store: sqlite3.Connection) -> None:
    for lookback in (10, 20, 30):
        assert take(store, look(configuration_hash({"lookback": lookback}))) is True
    with pytest.raises(BudgetExhaustedError, match="3 of 3 looks"):
        take(store, look(configuration_hash({"lookback": 40})))


def test_a_repeat_still_works_after_the_budget_is_exhausted(store: sqlite3.Connection) -> None:
    """A crash on the last look must not lock a researcher out of their own result."""
    digests = [configuration_hash({"lookback": n}) for n in (10, 20, 30)]
    for digest in digests:
        take(store, look(digest))
    assert take(store, look(digests[0])) is False, (
        "re-running an already recorded configuration was refused because the budget is spent, "
        "which punishes a crash and teaches people to work around the ledger"
    )


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
