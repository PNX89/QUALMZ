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

    `budget.py` hashes a CONFIGURATION, which is a different object: it identifies a look, never
    a dataset, and it is never compared against a provenance value. That file is allowed and
    named, so the exception is visible rather than implied by a pattern that happens to pass.
    """
    allowed = {"budget.py"}
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
