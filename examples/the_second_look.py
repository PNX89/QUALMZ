"""What a look budget does when a researcher runs the same thing twice.

    uv run python examples/the_second_look.py

NO DATABASE SERVER, NO INSTRUMENT, NO NETWORK. The budget's rule is a unique constraint, and
SQLite honours the same one PostgreSQL does, so this runs on a clone with nothing installed and
still exercises the real thing rather than a mock of it.
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from qualmz.budget import SCHEMA_SQL, BudgetExhaustedError, Look, configuration_hash, looks_taken

ALLOWED = 3


def main() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute(
            "insert into look_budget values ('momentum', '2024H2', ?, '2026-08-29')", (ALLOWED,)
        )

        print(f"momentum has {ALLOWED} looks at the 2024H2 holdout.")
        print()

        attempts = [
            ({"lookback": 20, "threshold": 0.5}, "the first idea"),
            ({"lookback": 20, "threshold": 0.5}, "the same thing again, after a crash"),
            ({"threshold": 0.5, "lookback": 20}, "the same thing with the keys reordered"),
            ({"lookback": 40, "threshold": 0.5}, "a longer lookback"),
            ({"lookback": 40, "threshold": 0.7}, "and a different threshold"),
            ({"lookback": 60, "threshold": 0.7}, "one more idea"),
        ]

        for configuration, description in attempts:
            digest = configuration_hash(configuration)
            try:
                fresh = take_one(connection, digest)
            except BudgetExhaustedError as refused:
                print(f"  {description:<42} REFUSED")
                print(f"      {refused}")
                break
            taken = looks_taken(connection, "momentum", "2024H2")
            print(
                f"  {description:<42} {'a new look' if fresh else 'not a new look'}"
                f"   {taken} of {ALLOWED} used"
            )

        print()
        print("  The second and third rows are the point. A crash and a reordered dictionary")
        print("  are the same configuration, so neither costs anything, and the count does not")
        print("  move. A changed parameter is a different question, so it does.")
        print()
        print("  The constraint is in the schema rather than in this file, so an insert that")
        print("  goes around it entirely still fails.")
    finally:
        connection.close()


def take_one(connection: sqlite3.Connection, digest: str) -> bool:
    from qualmz.budget import take

    return take(connection, Look("momentum", "2024H2", digest, "2026-08-29", "auc 0.51"))


if __name__ == "__main__":
    main()
