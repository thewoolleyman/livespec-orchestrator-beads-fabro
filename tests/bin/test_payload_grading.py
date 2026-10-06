"""Structural guard for the `_payload_grading` cut, plus its own boundary cases.

NOT a Red, and it should not be read as one. `_payload_grading.py` carries no
new behaviour: every function in it was MOVED verbatim out of `_payload.py`,
whose existing tests exercise them through the names `_payload` re-exports and
therefore already cover this file. The cut was forced by size — recording a
payload's source so an inherited tree is reused only when it came from the
same place took `_payload.py` past its 250 LLOC hard ceiling, and the remedy
for a file over the ceiling is cohesion decomposition, not line shaving.

What this file adds is the guard that the cut STAYS cut, and the two grading
cases whose only caller is now across a module boundary:

- the module exists and publishes the four names `_payload` imports back,
  so a future edit cannot quietly re-inline them;
- the names that had to become PUBLIC to cross the boundary are public, and
  the private spellings are GONE from `_payload` — a `_`-prefixed name
  imported from another module is rejected by pyright strict
  (`reportPrivateUsage`) and by the private-calls check alike;
- `IGNORED_NAMES` is ONE shared constant, because `_payload`'s `copytree` and
  this module's fidelity walk must agree on what the copy deliberately drops,
  and two constants could drift apart silently.

The module import is deferred into each test body via `importlib`, and the
first assertion is a genuine check on the module PATH, so this file reports a
missing module as a failed assertion rather than as a collection error.
"""

import importlib
import sys
from pathlib import Path
from typing import Any

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"
_GRADING_MODULE = _BIN_DIR / "_payload_grading.py"

# The names `_payload` imports back across the boundary. Each is PUBLIC for
# that reason alone.
_PUBLIC_SURFACE = (
    "IGNORED_NAMES",
    "fidelity_message",
    "incomplete_message",
    "missing_payload_paths",
    "payload_fidelity_gaps",
)
# The private spellings these carried while they lived in `_payload`. A
# cross-module import of any of them is what the private-calls check rejects.
_RETIRED_PRIVATE_NAMES = (
    "_IGNORED_NAMES",
    "_fidelity_message",
    "_incomplete_message",
    "_REQUIRED_FILES",
    "_REQUIRED_TREES",
    "_usable_tree",
)


def _import(*, name: str) -> Any:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    _ = sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_the_grading_module_exists_and_publishes_what_payload_imports_back() -> None:
    """The cut's public surface, asserted by name so it cannot be re-inlined."""
    assert _GRADING_MODULE.is_file(), f"the grading module was not cut out: {_GRADING_MODULE}"

    grading = _import(name="_payload_grading")

    for name in _PUBLIC_SURFACE:
        assert hasattr(grading, name), f"_payload_grading does not publish {name}"
        assert name in grading.__all__, f"{name} crosses a module boundary but is not in __all__"


def test_payload_reaches_the_grading_layer_through_its_public_names_only() -> None:
    """The retired private spellings are gone, so no private name is imported."""
    grading = _import(name="_payload_grading")
    payload = _import(name="_payload")

    for name in _RETIRED_PRIVATE_NAMES:
        assert not hasattr(payload, name), (
            f"_payload still carries {name}; a private name that crosses a module "
            "boundary is rejected by pyright strict and by the private-calls check"
        )
    for name in _PUBLIC_SURFACE:
        assert getattr(payload, name) is getattr(grading, name), (
            f"_payload's {name} is not the grading module's — the cut has drifted "
            "into two implementations"
        )


def test_the_ignored_names_tuple_is_shared_rather_than_restated() -> None:
    """One constant: `copytree` and the fidelity walk must agree on the drop set.

    `payload_fidelity_gaps` compares the copy against its source, and the copy
    deliberately omits these. Two separate constants would let the copy drop
    something the comparison still demands, which refuses every provision.
    """
    grading = _import(name="_payload_grading")

    assert grading.IGNORED_NAMES == ("__pycache__",)

    source = Path(_BIN_DIR).parent.parent
    assert source.is_dir(), "fixture: the plugin root did not resolve"
    gaps = grading.payload_fidelity_gaps(source_root=source, payload_root=source)
    assert gaps == (), f"a tree compared against itself reported gaps: {gaps}"


def test_a_truncated_fidelity_report_says_so_and_a_short_one_does_not(tmp_path: Path) -> None:
    """The cap's two arms, whose message text is now built across the boundary."""
    grading = _import(name="_payload_grading")

    capped = tuple(f"file-{index}.py" for index in range(grading.FIDELITY_REPORT_LIMIT))
    assert "possibly more" in grading.fidelity_message(root=tmp_path, gaps=capped)

    short = ("only-one.py",)
    assert "possibly more" not in grading.fidelity_message(root=tmp_path, gaps=short)


def test_an_incomplete_message_names_both_the_subject_and_what_is_missing(
    tmp_path: Path,
) -> None:
    """`subject` distinguishes an incomplete INSTALLATION from an incomplete COPY."""
    grading = _import(name="_payload_grading")

    detail = grading.incomplete_message(
        root=tmp_path, missing=("scripts/_vendor",), subject="installation"
    )

    assert "installation" in detail
    assert "scripts/_vendor" in detail
    assert "no factory run was started" in detail, "the zero-side-effect promise is missing"
