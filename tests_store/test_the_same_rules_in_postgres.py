"""The budget's constraint and the role's grant, against the store they are enforced in.

The offline suite runs the same schema against SQLite, which honours the unique constraint, so
the budget's rules are exercised for real there. Two things it cannot show:

    that PostgreSQL enforces the constraint the same way, which is worth checking rather than
    assuming, because a dialect difference here would move a budget into an honour system

    that the role-scoped grant refuses, because a grant is a PostgreSQL object. A barrier nobody
    has watched refuse is not a barrier, so the refusal is OBSERVED here rather than described.

THE SCHEMA AND THE GRANT ARE ADOPTED FROM A SIBLING and not invented here. QUIZZ owns the
holdout window and promotion tables and says so in its own source; this repository uses that
shape rather than a second one, because two repositories with two schemas for one idea is how
they end up disagreeing about what a holdout is.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

from qualmz.budget import SCHEMA_SQL, BudgetExhaustedError, Look, configuration_hash

DSN = os.environ.get("QUALMZ_POSTGRES", "postgresql://postgres@127.0.0.1:5432/postgres")

#: Adopted verbatim from the sibling that owns it. A role that can read the holdout definition
#: can compute the boundary exactly, and a barrier a caller can measure is one it can work around.
GRANT_SQL = "grant select on look to {role}"


@pytest.fixture
def store() -> Iterator[object]:
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("drop table if exists look, look_budget cascade")
            for statement in SCHEMA_SQL.split(";"):
                if statement.strip():
                    cursor.execute(statement.replace("?", "%s"))
            cursor.execute("insert into look_budget values ('momentum', '2024H2', 2, '2026-08-29')")
        yield connection


def take_look(connection: object, digest: str) -> None:
    with connection.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(
            "insert into look values (%s, %s, %s, %s, %s)",
            ("momentum", "2024H2", digest, "2026-08-29", "auc 0.51"),
        )


def test_postgres_refuses_the_duplicate_the_budget_depends_on(store: object) -> None:
    """The constraint, in the store where it is enforced for real."""
    psycopg = pytest.importorskip("psycopg")
    digest = configuration_hash({"lookback": 20})
    take_look(store, digest)
    with pytest.raises(psycopg.errors.UniqueViolation):
        take_look(store, digest)


def test_a_role_without_the_grant_cannot_read_the_ledger(store: object) -> None:
    """THE REFUSAL, WATCHED. A role that can read the ledger can compute the boundary."""
    psycopg = pytest.importorskip("psycopg")
    role = f"searcher_{uuid.uuid4().hex[:8]}"
    with store.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(f"create role {role} login password 'x'")
        cursor.execute(f"revoke all on look from {role}")

    dsn = DSN.split("://")[1].split("@")[1]
    with (
        psycopg.connect(f"postgresql://{role}:x@{dsn}", autocommit=True) as searcher,
        searcher.cursor() as cursor,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        cursor.execute("select count(*) from look")

    with store.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(GRANT_SQL.format(role=role))
    with (
        psycopg.connect(f"postgresql://{role}:x@{dsn}", autocommit=True) as searcher,
        searcher.cursor() as cursor,
    ):
        cursor.execute("select count(*) from look")
        assert cursor.fetchone() is not None, (
            "the grant was issued and the role still cannot read, so this test is passing for "
            "the wrong reason"
        )

    with store.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(f"drop owned by {role}")
        cursor.execute(f"drop role {role}")


def test_the_budget_still_refuses_after_the_last_look_in_postgres(store: object) -> None:
    """The rule, not just the constraint."""
    from qualmz import budget

    class Cursor:
        """The tiny shim that lets one implementation run against both stores.

        SQLite and psycopg differ in their placeholder and in whether `execute` returns a
        cursor. Rather than write the budget twice, the difference is absorbed here, in a test
        fixture, where it is visible.
        """

        def __init__(self, connection: object) -> None:
            self.connection = connection

        def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> Cursor:
            cursor = self.connection.cursor()  # type: ignore[attr-defined]
            cursor.execute(sql.replace("?", "%s"), parameters)
            self.cursor = cursor
            return self

        def fetchone(self) -> object:
            return self.cursor.fetchone()

    shim = Cursor(store)
    for lookback in (10, 20):
        budget.take(
            shim,
            Look(
                "momentum",
                "2024H2",
                configuration_hash({"lookback": lookback}),
                "2026-08-29",
                "auc 0.5",
            ),
        )
    with pytest.raises(BudgetExhaustedError, match="2 of 2 looks"):
        budget.take(
            shim,
            Look(
                "momentum", "2024H2", configuration_hash({"lookback": 30}), "2026-08-29", "auc 0.5"
            ),
        )
