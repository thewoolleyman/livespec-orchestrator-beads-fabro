"""The committed `dispatcher.overflow_factories` key, read and graded.

The factory-overflow-selection clause of `SPECIFICATION/contracts.md` gives this
key three outcomes, and keeping them three is the whole job of the module under
test. An ABSENT or EMPTY array means overflow selection is not configured, which
is an answer rather than a fault: "When it is absent or empty, selection is
exactly the order of" the registry section, "and nothing in this section
applies". A VIOLATING entry "MUST be refused before any item is claimed, with a
configuration finding naming the offending value". A well-formed array is the
candidate list — `dispatcher.default_factory` followed by each entry, in that
order.

WHY EACH REFUSAL NAMES THE OFFENDING VALUE AND ITS POSITION. Three of the four
faults the clause enumerates are about ONE entry of an array an operator may have
written several entries into, and two of them — a repeat, and a name equal to the
default — are only wrong in relation to something else in the same file. A message
saying only that the key is invalid sends an operator to read the whole array
back and guess which relation it violated.

WHY THE CANDIDATE LIST IS ASSERTED AS A SEQUENCE AND NOT AS A SET. Order decides
the answer: the clause breaks a utilization tie by taking "the earlier
candidate", and it fixes the default as the FIRST candidate. A set would satisfy
a membership assertion while leaving which factory wins a tie unspecified.

WHY A VIOLATING ARRAY YIELDS NO CANDIDATES RATHER THAN THE VALID PREFIX OF ONE.
Selection is the one thing that must not happen while the configuration is
refused: the refusal runs before any item is claimed, so a candidate list built
from the entries that happened to parse would be a list this dispatch is not
permitted to act on — and it would read exactly like a healthy one.

WHY ONE CASE PINS THE FACTORY-SELECTION ENVIRONMENT. The key is committed-only,
so the default it is graded against must come from the committed configuration;
`resolve_fabro_factory` is the obvious reader to reach for and it reads
`LIVESPEC_FABRO_FACTORY` first, which would make this grading depend on a shell
variable the dispatch has not even consulted yet.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_overflow_factories"
_MODULE_FILE = "_dispatcher_overflow_factories.py"

_DEFAULT = "hp"
_OVERFLOW = "petri"
_UNDECLARED = "ghost"
_KEY = "dispatcher.overflow_factories"


def _module() -> Any:
    """The module under test, imported inside the test body.

    The file is asserted FIRST so the Red is a genuine assertion failure rather
    than a collection error: at Red the module does not exist, and a top-level
    import of it would die before any assertion ran.
    """
    assert (_COMMANDS_DIR / _MODULE_FILE).is_file()
    return importlib.import_module(_MODULE_NAME)


def _write_config(*, cwd: Path, overflow: object | None = None) -> None:
    """A two-factory repository whose default is `hp`, optionally with the key.

    `overflow=None` writes NO `overflow_factories` key at all, which is the
    absent case; the empty-array case passes `[]` and is a different value this
    helper must not conflate with it.
    """
    dispatcher: dict[str, Any] = {
        "default_factory": _DEFAULT,
        "factories": {
            _DEFAULT: {"server": "https://hp.example.ts.net:32276"},
            _OVERFLOW: {"server": "https://petri.example.ts.net:32276"},
        },
    }
    if overflow is not None:
        dispatcher["overflow_factories"] = overflow
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def test_a_declared_array_yields_the_default_factory_followed_by_each_entry(
    tmp_path: Path,
) -> None:
    """The candidate order the clause fixes: default first, then each entry."""
    module = _module()
    _write_config(cwd=tmp_path, overflow=[_OVERFLOW])

    assert module.resolve_overflow_factories(cwd=tmp_path) == (_OVERFLOW,)
    assert module.overflow_candidates(cwd=tmp_path) == (_DEFAULT, _OVERFLOW)
    assert module.overflow_factories_refusal(repo=tmp_path) is None


@pytest.mark.parametrize(
    ("case", "overflow"),
    [("absent", None), ("empty", [])],
    ids=["absent", "empty"],
)
def test_an_absent_or_empty_key_configures_no_overflow_selection(
    tmp_path: Path,
    case: str,
    overflow: object | None,
) -> None:
    """Both spellings of "not configured" answer identically, and neither refuses.

    They are asserted TOGETHER because the clause names them together — "absent
    or empty" — and because an implementation testing only for the key's
    presence would read an empty array as a configured overflow with no entries,
    which is a candidate list of one and a capacity read nobody asked for.
    """
    del case
    module = _module()
    _write_config(cwd=tmp_path, overflow=overflow)

    assert module.resolve_overflow_factories(cwd=tmp_path) is None
    assert module.overflow_candidates(cwd=tmp_path) == ()
    assert module.overflow_factories_refusal(repo=tmp_path) is None


@pytest.mark.parametrize(
    ("case", "overflow", "fragments"),
    [
        ("not-an-array", _OVERFLOW, (_KEY, "array", repr(_OVERFLOW))),
        ("entry-not-a-string", [3], (f"{_KEY}[0]", repr(3))),
        ("entry-empty", [""], (f"{_KEY}[0]", repr(""))),
        ("undeclared", [_UNDECLARED], (f"{_KEY}[0]", "dispatcher.factories", repr(_UNDECLARED))),
        ("repeated", [_OVERFLOW, _OVERFLOW], (f"{_KEY}[1]", "repeat", repr(_OVERFLOW))),
        ("names-default", [_DEFAULT], (f"{_KEY}[0]", "dispatcher.default_factory", repr(_DEFAULT))),
    ],
    ids=[
        "not-an-array",
        "entry-not-a-string",
        "entry-empty",
        "undeclared",
        "repeated",
        "names-default",
    ],
)
def test_every_violating_entry_is_refused_naming_the_offending_value(
    tmp_path: Path,
    case: str,
    overflow: object,
    fragments: tuple[str, ...],
) -> None:
    """Each fault the clause enumerates refuses, and the message names the value.

    The POSITION is asserted alongside the value because the array may carry
    several entries and two of these faults — a repeat, and a name equal to the
    default — are violations only in relation to something else in the file, so a
    message naming neither leaves the operator to re-derive which relation broke.

    The REPEAT case names index 1 rather than 0: the first occurrence of a name
    is not the offence, and a message pointing at it would send an operator to
    delete the entry they meant to keep.
    """
    del case
    module = _module()
    _write_config(cwd=tmp_path, overflow=overflow)

    finding = module.resolve_overflow_factories(cwd=tmp_path)
    refusal = module.overflow_factories_refusal(repo=tmp_path)

    assert isinstance(finding, str)
    assert isinstance(refusal, str)
    for fragment in fragments:
        assert fragment in finding
        assert fragment in refusal
    # A refused configuration yields NO candidates: selection must not act on a
    # list assembled from whichever entries happened to parse.
    assert module.overflow_candidates(cwd=tmp_path) == ()


def test_the_committed_grading_ignores_the_factory_selection_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LIVESPEC_FABRO_FACTORY` moves neither the refusal nor the candidate order.

    The key is COMMITTED-only, so what it is graded against has to be the
    committed configuration and nothing a shell exported. The discriminating pair
    is asserted in one case because each half alone is satisfiable by the wrong
    implementation: an entry naming the committed default must still refuse while
    the environment names the other factory, and the candidate list must still
    open with the committed default rather than with the selected one. A reader
    resolving the default through the environment-aware path gets BOTH backwards
    — it admits the array the clause forbids and then puts the overflow factory
    first, where a utilization tie makes it win.
    """
    module = _module()
    monkeypatch.setenv("LIVESPEC_FABRO_FACTORY", _OVERFLOW)
    _write_config(cwd=tmp_path, overflow=[_DEFAULT])

    refusal = module.overflow_factories_refusal(repo=tmp_path)

    assert isinstance(refusal, str)
    assert repr(_DEFAULT) in refusal

    _write_config(cwd=tmp_path, overflow=[_OVERFLOW])

    assert module.overflow_candidates(cwd=tmp_path) == (_DEFAULT, _OVERFLOW)


def test_the_key_is_committed_only_and_declares_no_api_configurable_surface() -> None:
    """The clause says outright the key "is NOT declared API-configurable".

    Asserted against the committed API-configurable declaration rather than by
    reading the module, because the prohibition is about what the repository
    OFFERS: a reader of this module cannot tell whether some other surface
    declared the key settable.
    """
    module = _module()
    schema = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._drive_config_schema"
    )

    assert module.OVERFLOW_FACTORIES_KEY == "overflow_factories"
    assert module.OVERFLOW_FACTORIES_KEY not in {key.key for key in schema.CONFIG_KEYS}
