"""This repository consumes a data-provenance hash and never produces one.

The seam only means anything in one direction. If this repository could mint a hash, a promotion
could be made to pass by computing a new one, and the gate would be checking its own arithmetic
instead of the dataset's identity.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "src"

#: The functions worth naming. `hashlib.new("sha256")` is not in this set and does not need to
#: be: reaching it means importing hashlib, and an import of hashlib is itself an offence below.
DIGESTS = {"sha256", "md5", "blake2b"}


def modules() -> list[pathlib.Path]:
    found = sorted(SRC.rglob("*.py"))
    assert found, "there is no Python under src, so every check in this file is scanning nothing"
    return found


def hashing_sites(path: pathlib.Path) -> list[str]:
    """Every way this file reaches a hash, found by the imported NAME and not by one spelling.

    THE FIRST VERSION MATCHED `ast.Attribute` ALONE, which is the `hashlib.sha256(...)` spelling
    and nothing else. `from hashlib import sha256` produces an `ast.Name` call and was invisible,
    so a mint could be written into any module here with all three tests in this file green: it
    was written into divergence.py, it returned a real digest, and the suite stayed at 83 passed.

    So the import is the offence, whatever is done with it, and the bare call is caught too in
    case a digest ever arrives from somewhere other than hashlib.
    """
    sites: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "hashlib":
                    sites.append(f"{path.relative_to(REPO)}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "hashlib":
            sites.append(f"{path.relative_to(REPO)}:{node.lineno}: from {node.module} import")
        elif isinstance(node, ast.Attribute) and node.attr in DIGESTS:
            sites.append(f"{path.relative_to(REPO)}:{node.lineno}: {node.attr}")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in DIGESTS
        ):
            sites.append(f"{path.relative_to(REPO)}:{node.lineno}: {node.func.id}()")
    return sites


def imported_modules(path: pathlib.Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


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
    offenders = [
        site for path in modules() if path.name not in allowed for site in hashing_sites(path)
    ]
    assert offenders == [], (
        f"this repository computes a hash: {offenders}. It consumes a data-provenance hash "
        f"minted where the dataset was admitted, and minting one here would let a promotion "
        f"pass by producing its own"
    )


def test_the_two_files_allowed_to_hash_are_the_two_that_do() -> None:
    """An exception nobody needs any more is a standing permission to mint in that file."""
    hashing = {path.name for path in modules() if hashing_sites(path)}
    assert hashing == {"budget.py", "gates.py"}, (
        f"the files that compute a hash are {sorted(hashing)}, and the exception above names "
        f"budget.py and gates.py. Either the list is stale or a third file has started hashing"
    )


def test_the_configuration_hash_is_never_compared_against_a_provenance_hash() -> None:
    """Two hashes with two jobs, and confusing them would make the gate pass on anything."""
    text = (SRC / "qualmz" / "promotion.py").read_text(encoding="utf-8")
    assert "configuration_hash ==" not in text
    assert "provenance_sha256 != challenger.provenance_sha256" in text


def test_no_module_that_hashes_ever_mentions_a_provenance_value() -> None:
    """The assertion that makes the exception above narrow rather than a hole.

    A configuration hash and a golden digest are local objects. The provenance hash is not: it
    is minted where the dataset was admitted. If any comparison mixed them, this repository
    would be checking its own arithmetic and calling it a data version.

    EVERY MODULE, NOT THE TWO NAMED ONES. This read budget.py and gates.py by name, so a mint
    written into a third file was outside all three checks in this file at once, and a new module
    was covered on the commit that remembered to add it rather than on the commit that created
    it.
    """
    for path in modules():
        if not hashing_sites(path):
            continue
        assert "provenance" not in path.read_text(encoding="utf-8").lower(), (
            f"{path.relative_to(REPO)} computes a hash and mentions provenance. Those two things "
            f"must not meet: a local digest standing in for a data version is this repository "
            f"checking its own arithmetic"
        )


def test_the_gate_cannot_reach_a_locally_computed_hash() -> None:
    """The other direction, which the seam needs just as much.

    Nothing being minted in promotion.py is worth little if promotion.py can import a digest
    from a module that is allowed to mint one. The route was walked to be sure it is a route: a
    mint in divergence.py, imported into promotion.py, comparing a locally minted digest against
    a Result's provenance value and returning True on a hash this repository had just made for
    itself.
    """
    promotion = SRC / "qualmz" / "promotion.py"
    reachable = sorted(
        name
        for name in imported_modules(promotion)
        if name.split(".")[-1] in {"hashlib", "budget", "gates"}
    )
    assert reachable == [], (
        f"promotion.py imports {reachable}, so the gate that compares data versions can reach a "
        f"hash computed in this repository"
    )
    text = promotion.read_text(encoding="utf-8")
    for local in ("configuration_hash", "golden_digest", "hashlib"):
        assert f"{local}(" not in text, (
            f"promotion.py calls {local}(), so the gate that compares data versions can reach a "
            f"locally computed hash"
        )
