"""This repository consumes a data-provenance hash and never produces one.

The seam only means anything in one direction. If this repository could mint a hash, a promotion
could be made to pass by computing a new one, and the gate would be checking its own arithmetic
instead of the dataset's identity.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_nothing_here_computes_a_sha256() -> None:
    """A hash is minted where the dataset is admitted, which is not here.

    TWO FILES HASH SOMETHING, AND NEITHER HASHES A DATASET. `budget.py` hashes a CONFIGURATION,
    which identifies a look. `gates.py` hashes a PREDICTION SET, which pins what a model does.
    Neither is ever compared against a provenance value, and the test below asserts that
    separately, because "it is a different hash" is exactly what somebody would say about the
    wrong one. Both are named here so the exception is visible rather than implied by a pattern
    that happens to pass.
    """
    allowed = {"budget.py", "gates.py"}
    offenders: list[str] = []
    for path in sorted((REPO / "src").rglob("*.py")):
        if path.name in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"sha256", "md5", "blake2b"}:
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: {node.attr}")
    assert offenders == [], (
        f"this repository computes a hash: {offenders}. It consumes a data-provenance hash "
        f"minted where the dataset was admitted, and minting one here would let a promotion "
        f"pass by producing its own"
    )


def test_the_configuration_hash_is_never_compared_against_a_provenance_hash() -> None:
    """Two hashes with two jobs, and confusing them would make the gate pass on anything."""
    text = (REPO / "src" / "qualmz" / "promotion.py").read_text(encoding="utf-8")
    assert "configuration_hash ==" not in text
    assert "provenance_sha256 != challenger.provenance_sha256" in text


def test_neither_local_hash_is_ever_compared_against_a_provenance_value() -> None:
    """The assertion that makes the exception above narrow rather than a hole.

    A configuration hash and a golden digest are local objects. The provenance hash is not: it
    is minted where the dataset was admitted. If any comparison mixed them, this repository
    would be checking its own arithmetic and calling it a data version.
    """
    for name in ("budget.py", "gates.py"):
        text = (REPO / "src" / "qualmz" / name).read_text(encoding="utf-8")
        assert "provenance" not in text.lower(), (
            f"{name} mentions provenance, and it is one of the two files allowed to compute a "
            f"hash. Those two things must not meet"
        )

    promotion = (REPO / "src" / "qualmz" / "promotion.py").read_text(encoding="utf-8")
    for local in ("configuration_hash ==", "golden_digest(", "hashlib"):
        assert local not in promotion, (
            f"promotion.py uses {local!r}, so the gate that compares data versions can reach a "
            f"locally computed hash"
        )
