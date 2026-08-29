# QUALMZ

**A researcher gets a fixed number of looks at the holdout. The count is a row with a unique
constraint on the strategy, the configuration and the window, so re-running the same
configuration does not buy another one, and a crash does not cost one.**

[![CI](https://github.com/PNX89/QUALMZ/actions/workflows/ci.yml/badge.svg)](https://github.com/PNX89/QUALMZ/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

![A real run: a look budget of three, a crash and a reordered dictionary costing nothing, and
the fourth distinct configuration refused.](docs/demo.svg)

<!-- quoted from docs/evidence/demo.txt -->
```text
  the first idea                             a new look   1 of 3 used
  the same thing again, after a crash        not a new look   1 of 3 used
  the same thing with the keys reordered     not a new look   1 of 3 used
  a longer lookback                          a new look   2 of 3 used
```

The second and third rows are the argument. A crash and a reordered dictionary are the same
question, so neither costs anything. A changed parameter is a different question, so it does.

A counter in application code is decremented by a crash, a retry, a second worker, or a
researcher who reruns a cell. This is a constraint in the schema, so the second attempt fails at
the database on every path in, including an insert that goes around the API entirely.

**The holdout schema and the role-scoped grant are adopted from [QUIZZ](https://github.com/PNX89/QUIZZ)
rather than rebuilt.** That repository owns them and says so in its own source. Two repositories
with two schemas for one idea is how they end up disagreeing about what a holdout is, so this
one is smaller than it looks, on purpose.

One file to start with: [`src/qualmz/budget.py`](src/qualmz/budget.py).

## What has to be true before anything is promoted

Four gates, and each stops the promotion on its own:

| | what it asks | when it runs |
|---|---|---|
| **data validation** | is the frame the shape the model was built for? | before the model sees it |
| **model correctness** | does it still predict what it predicted? | against a pinned golden set |
| **performance** | does a batch still fit its budget? | best of several runs |
| **provenance** | were both models scored on the same data version? | against a hash minted elsewhere |

The pipeline is run twice, and the second run differs from the first in exactly one value: the
data version the challenger was scored on. It is refused, and every number in it is correct: the
comparison is between two things that differ in more than the model.

**This repository consumes a data-provenance hash and cannot mint one.** A test parses the source
and fails if anything here computes a SHA-256, naming the two files that hash a configuration and
a prediction set as allowed, with a second test asserting neither ever meets a provenance value.
If this could mint one, a promotion could be made to pass by producing a new hash.

The golden set was hollow for one commit: it computed the pinned digest from the same predictions
it then compared against, so it passed for any model at all. It is committed now, and changing
the model by one part in a million makes the harness exit non-zero.

## The halt is a task, not a line in a runbook

<!-- quoted from docs/evidence/halt/the-halt.txt -->
```text
  Condition result is False
  Skipping downstream tasks
  state=success
  tasks_skipped=1
```

That is Airflow's own output from a run with no approval recorded. Nothing downstream ran, and
**the run finished successful rather than failed**, which is the part worth arguing about: a
promotion waiting on a named human is not an incident, and a pipeline that pages somebody for one
is a pipeline whose alerts get muted within a fortnight.

Every gate is a short circuit rather than an assertion inside a task, for the same reason. The
approval does not default to yes, which is the single line worth reading in a file like that.

This is not Airflow in production and nothing here claims to have run it there. It is developed
against SQLite, of which Airflow's own documentation says: "There are plenty of limitations of
using the SQLite database which you can easily find online, and it should NEVER be used for
production."

## Live is underperforming the simulation. Bad luck, or a bug?

<!-- quoted from docs/evidence/divergence/bad-luck-or-a-bug.txt -->
```text
  a bug           0.000480     18.24      4.00   naive and block
  bad luck       -0.000284     -3.26     -0.95   naive
```

Two paired series of 500 days. The first has a persistent drag from a known day and both
statistics fire. The second has **no drift between the two series at all**, differing only by
noise that wanders, and the naive standard error calls it a bug.

Dividing by the square root of the number of days assumes each day is an independent
observation. A strategy holds positions across days, so a difference that appears on Monday is
still there on Tuesday, and the naive estimate is too small. Taking the standard error across 25
non-overlapping blocks gives -0.95, which is a fortnight of bad weeks.

Both series are generated from a fixed seed and **no capital was ever allocated**. Neither is a
record of anything traded, which is why the divergence in the first case starts on a day this
repository chose.

## Run it

The demo and the offline suite need nothing but Python. The budget's rule is a constraint SQLite
honours as well as PostgreSQL, so the offline suite exercises the real thing:

```text
uv run python examples/the_second_look.py
uv run pytest
```

The rest needs what it needs, and each has its own CI job:

```text
uv run --group store pytest tests_store -q
uv run python scripts/measure_divergence.py
uv run --group promotion python scripts/measure_promotion.py
scripts/measure_halt.sh
```

## What this does not do

It does not allocate capital, hold a track record, or claim any strategy makes money.

It does not make the information barrier unbreakable. A role without the grant cannot read the
ledger, which is watched refusing against a real PostgreSQL, and that is a different claim from
saying nobody can see the holdout: somebody with another route to the data has one.

The trial ledger is not complete either. It records the looks that went through it, and a
researcher who evaluated something outside it leaves no row. That is what the grant is for and
it is why the two are separate.

## Development

```text
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy .
```

<!-- toolset:start -->

Part of the Q...Z toolset, all of it designing for the failure that does not announce itself:

- [QUACKZ](https://github.com/PNX89/QUACKZ), deflating a backtest that only looks good because
  it was picked out of two hundred.
- [QUOTEZ](https://github.com/PNX89/QUOTEZ), market data an agent can read and cannot act on.
- [QUELLZ](https://github.com/PNX89/QUELLZ), measuring what prompt-injection containment costs
  in utility as well as in attack rate.
- [QUIDZ](https://github.com/PNX89/QUIDZ), refusing the outbound payment that would have gone
  out twice.
- [QUESTZ](https://github.com/PNX89/QUESTZ), stopping a scraper before it writes a CSV from a
  page that changed shape.
- [QUIZZ](https://github.com/PNX89/QUIZZ), answering what a statistic said at the time, and
  refusing when it cannot.
- [QUARANTINEZ](https://github.com/PNX89/QUARANTINEZ), treating an outcome the venue never
  confirmed as terminal rather than as a retry.
- [QUENCHZ](https://github.com/PNX89/QUENCHZ), deciding in the open what a tool server gets free
  while it is still somebody's subprocess.
- [QUILTZ](https://github.com/PNX89/QUILTZ), proving infrastructure code wrong without a cloud
  account, and saying what that cannot show.
- [QUAYZ](https://github.com/PNX89/QUAYZ), telling a crash loop from an OOMKill, and naming the
  failure that no single field finds.
- [QUARRYZ](https://github.com/PNX89/QUARRYZ), keeping every version a statistical office
  published, and failing the build when it quietly issues another.
- [QUASHZ](https://github.com/PNX89/QUASHZ), refusing a row whose outcome had not been decided
  yet when the decision would have been made.
- QUALMZ, this one: a fixed number of looks at the holdout, where re-running the same
  configuration does not buy another.
- [QUEUEZ](https://github.com/PNX89/QUEUEZ), ordering a feed by its sequence, because on a real
  recorded session the clock goes backwards.

**On QUIZZ.** QUIZZ owns the holdout window and promotion schema and the role-scoped grant that
goes with them, and says so in its own source. This repository adopts both rather than inventing
a second shape for one idea, which is why it is smaller than it looks. The direction matters:
inventing another schema for one holdout is how a pair of repositories end up disagreeing about
what was held back and when.

<!-- toolset:end -->

## Licence

MIT.
