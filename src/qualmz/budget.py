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


class BudgetExhaustedError(RuntimeError):
    """Raised when a NEW configuration would exceed the looks granted for a window."""


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
    """
    if not configuration:
        raise ValueError("an empty configuration cannot identify a look")
    payload = json.dumps(configuration, sort_keys=True, separators=(",", ":"), default=str)
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

    allowed = looks_allowed(connection, look.strategy, look.holdout_window)
    taken = looks_taken(connection, look.strategy, look.holdout_window)
    if taken >= allowed:
        raise BudgetExhaustedError(
            f"{look.strategy!r} has taken {taken} of {allowed} looks at {look.holdout_window!r}, "
            f"and this configuration has not been evaluated before, so it would be the "
            f"{taken + 1}th"
        )

    connection.execute(
        "insert into look values (?, ?, ?, ?, ?)",
        (
            look.strategy,
            look.holdout_window,
            look.configuration_hash,
            look.looked_on,
            look.result,
        ),
    )
    return True
