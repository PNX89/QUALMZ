"""The look budget, and the constraint that makes it one.

THE CLAIM. A researcher gets a fixed number of looks at a held out window. The count is a row,
not a counter in a process, and the row carries a unique constraint on the strategy, the
configuration hash and the window. **Re-running the same configuration does not buy a fresh
look**, which is the difference between a budget and a suggestion.

WHY THAT CONSTRAINT AND NOT A COUNTER. A counter incremented in application code is decremented
by a crash, a retry, a second worker, or a researcher who reruns the cell. A unique constraint is
enforced by the store, so the second attempt at the same configuration fails at the database
rather than at the honour system, and the failure is the same on every path into it.

WHAT A LOOK IS. One evaluation of one configuration against one window. The configuration hash
covers everything that changes what is evaluated, so a changed parameter is a NEW look and
costs one, while a rerun of an identical configuration is the SAME look and costs nothing. Both
halves matter: a budget that charges for reruns punishes a crash, and a budget that charges
nothing for a changed parameter is not a budget.

WHAT THIS CANNOT DO. It cannot stop somebody looking at the window through a path that does not
go through this table. That is what the role-scoped grant is for, and the grant is adopted from
a sibling rather than reinvented here.

AND THE TWO HALVES ARE NOT ENFORCED EQUALLY, which is worth saying plainly because the argument
above reads as though they are. The REPEAT is a unique constraint, so it is refused by the store
on every path in, including an insert that never came through this file. The CAP is a count, and
SQL has nowhere to put a constraint relating the number of rows in one table to a column of
another, so it is one statement rather than a constraint: an insert that goes around this API
can still push the count past the grant, and against PostgreSQL at READ COMMITTED two concurrent
transactions can as well.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

#: The two statements, in the dialect both stores accept, so the same rules run against SQLite
#: in the offline suite and against PostgreSQL where they are enforced for real.
SCHEMA_SQL = """
create table if not exists look_budget (
    strategy       text not null,
    holdout_window text not null,
    looks_allowed  integer not null,
    granted_on     text not null,
    primary key (strategy, holdout_window)
);
create table if not exists look (
    strategy           text not null,
    holdout_window     text not null,
    configuration_hash text not null,
    looked_on          text not null,
    result             text not null,
    -- THE WHOLE POINT OF THE FILE. Three columns, one constraint. A second evaluation of the
    -- same configuration against the same window cannot be inserted, so it cannot be counted,
    -- so re-running does not buy anything.
    primary key (strategy, holdout_window, configuration_hash)
);
"""


#: The look is counted and written in ONE statement, so nothing of this repository's holds
#: between the two. It read the count, compared it, and inserted, which is the application-code
#: counter this file argues against written in three lines of Python: two workers evaluating two
#: different configurations both passed the comparison and both inserted, and a budget of three
#: recorded four looks with nothing raised.
#:
#: WHAT ONE STATEMENT DOES AND DOES NOT CLOSE, measured rather than assumed. Against SQLite,
#: which serialises its writers, the two workers above cannot both pass. Against PostgreSQL 17.10
#: at its default READ COMMITTED, two concurrent transactions each take their snapshot before the
#: other commits, so both subqueries still count two and the ledger still reaches four. Closing
#: that needs a lock held across statements (`for update`), which SQLite does not have, or a
#: caller that runs this inside a transaction, which this signature cannot promise. So the window
#: is a statement rather than three, and the paragraph at the top of this file says the rest.
COUNT_THEN_INSERT = (
    "insert into look "
    "select ?, ?, ?, ?, ? "
    "where (select count(*) from look where strategy = ? and holdout_window = ?) "
    "< (select looks_allowed from look_budget where strategy = ? and holdout_window = ?) "
    "returning 1"
)


class BudgetExhaustedError(RuntimeError):
    """Raised when a NEW configuration would exceed the looks granted for a window."""


def _ordinal(n: int) -> str:
    """The English ordinal suffix, with the eleven, twelve and thirteen exception checked first.

    THIS READ f"{n}th" UNCONDITIONALLY, which is the researcher's own refusal message and is
    correct only for a budget of exactly three, where the refused look is the fourth. A budget
    of one, two, twenty, twenty-one or twenty-two produced "2th", "3th", "21th" and "22th" in the
    same sentence. The exception is checked before the last digit because 11, 12 and 13 take
    "th" regardless of what looking at the last digit alone would say.
    """
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


@dataclass(frozen=True)
class Look:
    """One evaluation of one configuration against one window."""

    strategy: str
    holdout_window: str
    configuration_hash: str
    looked_on: str
    result: str


def configuration_hash(configuration: dict[str, Any]) -> str:
    """A stable hash over everything that changes what is evaluated.

    SORTED KEYS AND A CANONICAL SEPARATOR, so two dictionaries that differ only in the order
    they were built in hash the same. Without that, a researcher who reordered their parameters
    would buy a second look at the same configuration, which is the loophole this is for.

    AND NOTHING IS STRINGIFIED ON THE WAY IN. This took trouble over key order and then handed
    every value json could not represent to `str`, which broke the same claim in both
    directions. A set's repr depends on per-process string hash randomisation, so one
    configuration holding a set of feature names hashed three different ways in five fresh
    processes, and a researcher rerunning the same cell after a crash bought a fresh look every
    time. In the other direction, a long array's repr elides its middle, so two genuinely
    different parameter vectors hashed identically and a changed parameter cost nothing. A value
    that cannot be written down is refused instead, for the same reason the empty configuration
    above is: it cannot identify a look.
    """
    if not configuration:
        raise ValueError("an empty configuration cannot identify a look")
    try:
        payload = json.dumps(configuration, sort_keys=True, separators=(",", ":"))
    except TypeError as unrepresentable:
        raise ValueError(
            f"this configuration holds a value json cannot represent ({unrepresentable}), and "
            f"hashing its text instead would make one configuration hash differently in every "
            f"process. Hand it something a reader could write down: a sorted list for a set, a "
            f"list for an array, an ISO string for a date"
        ) from unrepresentable
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def looks_taken(connection: Any, strategy: str, window: str) -> int:
    """How many DISTINCT configurations have been evaluated against this window."""
    row = connection.execute(
        "select count(*) from look where strategy = ? and holdout_window = ?",
        (strategy, window),
    ).fetchone()
    return int(row[0])


def looks_allowed(connection: Any, strategy: str, window: str) -> int:
    row = connection.execute(
        "select looks_allowed from look_budget where strategy = ? and holdout_window = ?",
        (strategy, window),
    ).fetchone()
    if row is None:
        raise BudgetExhaustedError(
            f"no budget has been granted for {strategy!r} against {window!r}, and an ungranted "
            f"budget is zero rather than unlimited"
        )
    return int(row[0])


def take(connection: Any, look: Look) -> bool:
    """Record a look. Returns True if it was new, False if this configuration was already seen.

    THE RETURN VALUE IS THE INTERESTING PART. A repeat is not an error: a researcher who reruns
    a notebook after a crash has not done anything wrong, and raising would push them towards
    working around the ledger. It is simply not a new look, and the count does not move.
    """
    already = connection.execute(
        "select 1 from look where strategy = ? and holdout_window = ? and configuration_hash = ?",
        (look.strategy, look.holdout_window, look.configuration_hash),
    ).fetchone()
    if already is not None:
        return False

    recorded = connection.execute(
        COUNT_THEN_INSERT,
        (
            look.strategy,
            look.holdout_window,
            look.configuration_hash,
            look.looked_on,
            look.result,
            look.strategy,
            look.holdout_window,
            look.strategy,
            look.holdout_window,
        ),
    ).fetchone()
    if recorded is not None:
        return True

    # NOTHING WAS INSERTED, so either the budget is spent or none was ever granted. The count is
    # read here to write a sentence a researcher can act on, and not to decide anything: the
    # decision was made by the statement above.
    allowed = looks_allowed(connection, look.strategy, look.holdout_window)
    taken = looks_taken(connection, look.strategy, look.holdout_window)
    raise BudgetExhaustedError(
        f"{look.strategy!r} has taken {taken} of {allowed} looks at {look.holdout_window!r}, "
        f"and this configuration has not been evaluated before, so it would be the "
        f"{_ordinal(taken + 1)}"
    )
