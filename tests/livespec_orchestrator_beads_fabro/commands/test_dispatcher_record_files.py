"""The `generator` key of a committed `dispatcher.record_files` entry, as graded.

The declared-record-file clause of `SPECIFICATION/contracts.md` says that "Any
entry MAY also name `generator`, a non-empty argv array run from the repository
root that rewrites the file at `path` from the repository's tree", and that "A
file whose entry names a generator is a GENERATED record file". This is the
configuration surface that admits such a declaration, and the only part of it
measurable inside a sandbox: Scenario 238's refresh behaviour is produced by the
graph's own command scripts against a RELEASED payload, so it is captured on an
operator host rather than proved here.

WHY THE RESOLUTION IS POSITIONAL AND SAYS NOTHING ABOUT `path` OR `format`. The
same ratified paragraph governs the entry-wise merge of Scenario 200, whose
`path` / `format` / `key` parse is a separate TODO owned by work-item
bd-ib-davaxq and is not implemented. A reader that graded those keys here would
be a second authority on the entry grammar, and the two would drift in the
direction nothing announces: both would still produce a well-formed entry list.
So the resolution carries ONE slot per declared entry holding that entry's
generator argv, or `None` where the entry declares none, and a later consumer
joins those positions with the full entry parse that item adds.

WHY EVERY REFUSAL NAMES THE POSITION AS WELL AS THE KEY. `record_files` is an
array an operator may have written several entries into, and only one of them is
the offence. A message naming `dispatcher.record_files.generator` would leave the
operator to read the whole array back and guess which entry it meant, which is
the same reason the `dispatcher.overflow_factories` findings name an index.

WHY AN ABSENT `generator` IS ACCEPTED RATHER THAN DEFAULTED. The clause makes it
optional — a `json-array` or `markdown-insertions` entry that no generator
rewrites is the ordinary case — so an entry declaring none is an ANSWER and not a
fault. `None` in a slot and a refusal are therefore different outcomes, and an
implementation collapsing them would refuse every repository that declares a
record file at all.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_record_files"
_MODULE_FILE = "_dispatcher_record_files.py"

_KEY = "dispatcher.record_files"
# A generator argv carrying no fleet-toolchain literal, so this fixture states
# the shape the clause admits without pinning which runner a repository uses.
_GENERATOR = ["tools/generate-register", "--write"]
_REGISTER = "tests/heading-coverage-debt.json"
_REGISTRY = "tests/heading-coverage.json"


def _module() -> Any:
    """The module under test, imported inside the test body.

    The file is asserted FIRST so the Red is a genuine assertion failure rather
    than a collection error: at Red the module does not exist, and a top-level
    import of it would die before any assertion ran.
    """
    assert (_COMMANDS_DIR / _MODULE_FILE).is_file()
    return importlib.import_module(_MODULE_NAME)


def _write_config(*, cwd: Path, record_files: object | None = None) -> None:
    """A repository whose dispatcher block optionally declares the key.

    `record_files=None` writes NO `record_files` key at all, which is the absent
    case; the empty-array case passes `[]` and is a different value this helper
    must not conflate with it.
    """
    dispatcher: dict[str, Any] = {"default_factory": "hp"}
    if record_files is not None:
        dispatcher["record_files"] = record_files
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def test_an_entry_naming_a_non_empty_generator_argv_of_strings_is_accepted(
    tmp_path: Path,
) -> None:
    """The clause's own admitted declaration resolves, and refuses nothing.

    Asserted as a TUPLE rather than a list because the argv is carried onward to
    a consumer that must not be able to mutate it, and the slot is positional so
    a declaration of several entries can be joined back to them.
    """
    module = _module()
    _write_config(
        cwd=tmp_path,
        record_files=[
            {"path": _REGISTER, "format": "json-array", "generator": _GENERATOR},
        ],
    )

    assert module.resolve_record_file_generators(cwd=tmp_path) == ((*_GENERATOR,),)
    assert module.record_file_generators_refusal(repo=tmp_path) is None


def test_an_entry_that_names_no_generator_is_accepted_and_declares_none(
    tmp_path: Path,
) -> None:
    """An optional key left unwritten is an answer, not a fault.

    The slot holds `None` rather than an empty tuple: an empty argv is not a
    command anyone could run, so a reader coercing the two together would hand a
    consumer something it would try to execute.
    """
    module = _module()
    _write_config(
        cwd=tmp_path,
        record_files=[
            {"path": _REGISTRY, "format": "json-array", "key": ["heading"]},
            {"path": _REGISTER, "format": "json-array", "generator": _GENERATOR},
        ],
    )

    assert module.resolve_record_file_generators(cwd=tmp_path) == (None, (*_GENERATOR,))
    assert module.record_file_generators_refusal(repo=tmp_path) is None


@pytest.mark.parametrize(
    ("case", "record_files"),
    [("absent", None), ("empty", [])],
    ids=["absent", "empty"],
)
def test_an_absent_or_empty_key_declares_no_record_files(
    tmp_path: Path,
    case: str,
    record_files: object | None,
) -> None:
    """Both spellings of "declares no record files" answer identically.

    The clause names them together — "An absent key declares no record files" —
    and an implementation testing only for the key's presence would read `[]` as
    a declaration of zero entries, which is the same answer reached a way that
    cannot be told apart from a reader that failed to parse it.
    """
    del case
    module = _module()
    _write_config(cwd=tmp_path, record_files=record_files)

    assert module.resolve_record_file_generators(cwd=tmp_path) is None
    assert module.record_file_generators_refusal(repo=tmp_path) is None


@pytest.mark.parametrize(
    ("case", "record_files", "fragments"),
    [
        ("key-not-an-array", {"path": _REGISTER}, (_KEY, "array")),
        ("entry-not-a-mapping", ["just-a-string"], (f"{_KEY}[0]", repr("just-a-string"))),
        (
            "generator-not-an-array",
            [{"path": _REGISTER, "generator": "tools/generate-register"}],
            (f"{_KEY}[0].generator", repr("tools/generate-register")),
        ),
        (
            "generator-empty",
            [{"path": _REGISTER, "generator": []}],
            (f"{_KEY}[0].generator", repr([])),
        ),
        (
            "generator-element-not-a-string",
            [{"path": _REGISTER, "generator": ["tools/generate-register", 3]}],
            (f"{_KEY}[0].generator", repr(["tools/generate-register", 3])),
        ),
        (
            "generator-element-empty",
            [{"path": _REGISTER, "generator": ["tools/generate-register", ""]}],
            (f"{_KEY}[0].generator", repr(["tools/generate-register", ""])),
        ),
    ],
    ids=[
        "key-not-an-array",
        "entry-not-a-mapping",
        "generator-not-an-array",
        "generator-empty",
        "generator-element-not-a-string",
        "generator-element-empty",
    ],
)
def test_a_malformed_generator_is_refused_naming_that_entrys_generator_key(
    tmp_path: Path,
    case: str,
    record_files: object,
    fragments: tuple[str, ...],
) -> None:
    """Each malformed declaration refuses, and the message names key and value.

    The VALUE is asserted alongside the key because the operator has to see what
    was read: `generator` holding a bare command string and `generator` holding
    an empty array are both "not a non-empty array of strings", and a message
    carrying only the key cannot tell them apart.

    A refused declaration yields NO generators, rather than the slots that
    happened to parse: the refusal exists to precede a refresh that would run one
    of them, and a list assembled from the survivors would read exactly like a
    healthy one.
    """
    del case
    module = _module()
    _write_config(cwd=tmp_path, record_files=record_files)

    finding = module.resolve_record_file_generators(cwd=tmp_path)
    refusal = module.record_file_generators_refusal(repo=tmp_path)

    assert isinstance(finding, str)
    assert isinstance(refusal, str)
    for fragment in fragments:
        assert fragment in finding
        assert fragment in refusal


def test_the_refusal_names_the_offending_entrys_own_position(tmp_path: Path) -> None:
    """A later entry's fault is reported at ITS index, not at the array's.

    This is the discriminating case for the positional naming: an implementation
    that reported `dispatcher.record_files.generator`, or that always reported
    index 0, satisfies every single-entry case above while sending an operator to
    edit the one entry in the file that is correct.
    """
    module = _module()
    _write_config(
        cwd=tmp_path,
        record_files=[
            {"path": _REGISTRY, "format": "json-array", "generator": _GENERATOR},
            {"path": _REGISTER, "format": "json-array", "generator": []},
        ],
    )

    finding = module.resolve_record_file_generators(cwd=tmp_path)

    assert isinstance(finding, str)
    assert f"{_KEY}[1].generator" in finding
    assert f"{_KEY}[0]" not in finding
