"""The aggregate declares whether each member reads only its committed tree."""

from __future__ import annotations

import re
from pathlib import Path

from livespec_dev_tooling.check_inventory import inventory_members
from livespec_dev_tooling.check_purity import audit_check_purity
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECK_RECIPE_HEADER = re.compile(r"^check:[ \t]*$")
_ARRAY_START = re.compile(r"^[ \t]*targets=\([ \t]*$")
_ARRAY_END = re.compile(r"^[ \t]*\)[ \t]*$")


def _aggregate_targets() -> tuple[str, ...]:
    """Return the `check:` recipe members without reusing its shell extractor."""
    in_recipe = False
    in_array = False
    targets: list[str] = []
    for line in (_REPO_ROOT / "justfile").read_text(encoding="utf-8").splitlines():
        if not in_recipe:
            in_recipe = _CHECK_RECIPE_HEADER.match(line) is not None
            continue
        if line and not line.startswith((" ", "\t")) and ":" in line:
            break
        if not in_array:
            in_array = _ARRAY_START.match(line) is not None
            continue
        if _ARRAY_END.match(line) is not None:
            break
        target = line.split("#", 1)[0].strip()
        if target.startswith("check-"):
            targets.append(target)
    return tuple(targets)


def test_every_aggregate_member_declares_its_purity() -> None:
    """A token must never silently treat an undeclared member as memoizable."""
    result = audit_check_purity(targets=_aggregate_targets(), repo_root=_REPO_ROOT)

    assert is_successful(result)
    assert unsafe_perform_io(result.unwrap()).undeclared == ()


def test_purity_inventory_matches_the_aggregate_members() -> None:
    """The annotation inventory cannot silently drift from `just check`."""
    inventory = _REPO_ROOT / "check-targets.txt"

    assert inventory.is_file()
    assert tuple(member.name for member in inventory_members(text=inventory.read_text())) == (
        _aggregate_targets()
    )
