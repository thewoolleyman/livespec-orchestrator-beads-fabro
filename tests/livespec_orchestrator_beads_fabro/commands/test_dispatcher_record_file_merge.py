"""The materialized declared-record-file merger, as an artifact.

Scenario 200's behaviour is exercised end to end against the shipped stage bytes
in `tests/integration/test_record_file_refresh_merge_scenario200.py`. What is
left here is what that test cannot see: the properties of the PROGRAM ITSELF.

Two of those properties decide whether the arm is safe at all. A merger that
resolved a file this repository did not DECLARE would rewrite arbitrary source
during a refresh with no human in the loop; and a merger that resolved an object
BOTH sides changed differently would pick a winner silently, which is the one
thing `SPECIFICATION/contracts.md` section "Declared record files merge without
a repair round" forbids it to do. Neither can be reached behaviourally without
constructing a run whose
whole point is that it must NOT be merged, so both are graded here, against the
exact bytes the prepare step lands in the sandbox.

The third is the reason this file loads the program by path rather than importing
the package: the governed clone has no copy of
`livespec_orchestrator_beads_fabro`, so a merger that worked only where that
package happens to be importable is broken in exactly the way no behavioural
case can reach.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_path_expansion,
    record_file_merge_program_prepare_steps_block,
    record_file_merge_program_source,
)

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
)
_MODULE_PATH = _COMMANDS / "_dispatcher_record_file_merge.py"

_JSON_ENTRY = {"path": "record.json", "format": "json-array", "key": ["id"]}
_MARKDOWN_ENTRY = {"path": "notes.md", "format": "markdown-insertions"}


def _json_sides(*, dash: str) -> tuple[str, str, str]:
    """The three sides of a record whose UNTOUCHED entry spells an em dash as `dash`.

    One helper rather than six literals because the escaped and the raw spelling
    differ by a single backslash, and a reader cannot see which literal is which
    when the two sit side by side. The sides are built from one shared object, so
    the only difference between the two calls is the spelling under test.
    """
    shared = '{"id": "shared", "note": "a ' + dash + ' dash"}'
    return (
        f"[{shared}]\n",
        f'[{shared}, {{"id": "default"}}]\n',
        f'[{shared}, {{"id": "run"}}]\n',
    )


_DECLARATION = """{
  // A comment, because the committed declaration this reads is JSONC.
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "record_files": [
        {"path": "record.json", "format": "json-array", "key": ["id"]},
        {"path": "notes.md", "format": "markdown-insertions"}
      ]
    }
  }
}
"""


def _materialized(*, tmp_path: Path) -> ModuleType:
    """The sandbox program as a module, loaded from the bytes the prepare step writes.

    Written under its own filename exactly as the prepare step lands it, so the
    import this performs is the import the sandbox performs.
    """
    path = tmp_path / RECORD_FILE_MERGE_PROGRAM_FILENAME
    _ = path.write_text(record_file_merge_program_source(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("livespec_record_file_merge", path)
    assert spec is not None
    assert spec.loader is not None
    program = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(program)
    return program


def test_a_json_array_record_keeps_the_default_order_then_the_runs_additions(
    tmp_path: Path,
) -> None:
    """The merged array is the default branch's order with the run's additions appended.

    The three objects are deliberately arranged so a merger that simply
    concatenated the two sides, or that kept the RUN's order, would produce a
    different list: `shared` is untouched by either side and must keep the
    default branch's position, `default` precedes `run` only because the default
    branch is the side whose order is authoritative, and the run's own object
    must survive rather than be dropped as the side the rebase replays.
    """
    program = _materialized(tmp_path=tmp_path)

    merged, from_default, from_run = program.merged_record(
        entry=_JSON_ENTRY,
        base='[{"id": "shared"}]\n',
        default='[{"id": "shared"}, {"id": "default"}]\n',
        run='[{"id": "shared"}, {"id": "run"}]\n',
    )

    assert json.loads(merged) == [{"id": "shared"}, {"id": "default"}, {"id": "run"}]
    assert [object_["id"] for object_ in json.loads(merged)] == ["shared", "default", "run"]
    assert (from_default, from_run) == (2, 1)


def test_a_json_array_record_each_side_removed_a_different_object_from_loses_both(
    tmp_path: Path,
) -> None:
    """Scenario 200's first sub-scenario, which is a REMOVAL on both sides.

    The measured collision this item was filed for is two revise passes each
    discharging a different heading's coverage debt, so each side's change to
    `tests/heading-coverage-debt.json` is a removal rather than an addition. A
    merger that took "the side that changed it" as the side that still HAS the
    object would resurrect both, and the file would then still claim debt the
    default branch had already discharged.
    """
    program = _materialized(tmp_path=tmp_path)

    merged, from_default, from_run = program.merged_record(
        entry=_JSON_ENTRY,
        base='[{"id": "a"}, {"id": "b"}, {"id": "c"}]\n',
        default='[{"id": "b"}, {"id": "c"}]\n',
        run='[{"id": "a"}, {"id": "c"}]\n',
    )

    assert json.loads(merged) == [{"id": "c"}]
    assert (from_default, from_run) == (1, 0)


def test_a_json_array_record_is_rewritten_in_the_encoding_its_own_sides_carry(
    tmp_path: Path,
) -> None:
    """An entry neither side touched stays as it is ON DISK, not only in the parse.

    Both JSON records this arm was built for are committed ASCII-escaped, and a
    merger that fixed its own serialization would re-encode every untouched entry
    of them: a two-entry merge arrives as a whole-file diff in the one artifact an
    operator reads to reconstruct what the merge did, it ping-pongs against the
    canonical writer on the next ordinary edit, and — against this arm's own
    purpose — it widens the conflict surface in exactly these files for every
    in-flight run whose base predates the flip. Nothing downstream catches it,
    because every reader of these records parses rather than compares bytes.

    The two halves are ONE case because either alone is satisfied by a merger
    that simply fixed the OTHER spelling: escaping everything keeps the escaped
    record and mangles the raw one, and escaping nothing does the reverse. The
    final assertion is what makes them halves of one claim rather than two
    unrelated expectations — the merged CONTENT is identical, so the difference
    under test is the encoding and nothing else.
    """
    program = _materialized(tmp_path=tmp_path)
    base, default, run = _json_sides(dash="\\u2014")
    escaped, _, _ = program.merged_record(entry=_JSON_ENTRY, base=base, default=default, run=run)
    base, default, run = _json_sides(dash="—")
    raw, _, _ = program.merged_record(entry=_JSON_ENTRY, base=base, default=default, run=run)

    assert escaped.isascii()
    assert '"note": "a \\u2014 dash"' in escaped
    assert not raw.isascii()
    assert '"note": "a — dash"' in raw
    assert json.loads(escaped) == json.loads(raw)


def test_a_json_array_record_object_both_sides_changed_differently_is_refused(
    tmp_path: Path,
) -> None:
    """The one case the arm must hand back rather than decide.

    The control for the merge cases above: both sides reach the SAME key, so a
    merger that had stopped comparing the two results would return a perfectly
    well-formed array naming one side's value, and the refresh would publish a
    silent overwrite that no diff in the run announces as a choice.
    """
    program = _materialized(tmp_path=tmp_path)

    with pytest.raises(program.RecordFileMergeUnresolvable) as refusal:
        _ = program.merged_record(
            entry=_JSON_ENTRY,
            base='[{"id": "shared", "test": "TODO"}]\n',
            default='[{"id": "shared", "test": "tests.a"}]\n',
            run='[{"id": "shared", "test": "tests.b"}]\n',
        )

    assert "shared" in str(refusal.value)


def test_a_json_array_record_whose_merge_would_repeat_a_key_is_refused(
    tmp_path: Path,
) -> None:
    """A merged array holding two objects with the same key is not resolvable.

    Reached through a side that itself repeats the key, which is the only way the
    condition can arise: the merge indexes BY key, so this is the input that
    would otherwise make one of the two silently disappear during the index.
    """
    program = _materialized(tmp_path=tmp_path)

    with pytest.raises(program.RecordFileMergeUnresolvable):
        _ = program.merged_record(
            entry=_JSON_ENTRY,
            base='[{"id": "shared"}]\n',
            default='[{"id": "shared"}, {"id": "dup"}, {"id": "dup"}]\n',
            run='[{"id": "shared"}]\n',
        )


def test_a_markdown_record_holds_the_defaults_inserted_lines_then_the_runs(
    tmp_path: Path,
) -> None:
    """Both sides' insertions survive, in the ratified order, at the same position.

    This is the `tests/integration/CLAUDE.md` collision: two runs each append
    their own bullet to the end of the same registry. A merger that kept one
    side would silently drop a test file's only documentation, and one that
    interleaved them would split a multi-line bullet.
    """
    program = _materialized(tmp_path=tmp_path)

    merged, from_default, from_run = program.merged_record(
        entry=_MARKDOWN_ENTRY,
        base="- base bullet\n",
        default="- base bullet\n- default bullet\n  continued\n",
        run="- base bullet\n- run bullet\n",
    )

    assert merged == "- base bullet\n- default bullet\n  continued\n- run bullet\n"
    assert (from_default, from_run) == (2, 1)


def test_a_markdown_record_both_sides_rewrote_the_same_line_of_is_refused(
    tmp_path: Path,
) -> None:
    """The Markdown control: a base line both sides touched is not an insertion.

    Without it, "the merge resolved" would be equally consistent with a merger
    that appends every difference it finds, which would drop one side's rewrite
    of a shared line without reporting that it chose.
    """
    program = _materialized(tmp_path=tmp_path)

    with pytest.raises(program.RecordFileMergeUnresolvable):
        _ = program.merged_record(
            entry=_MARKDOWN_ENTRY,
            base="- shared bullet\n",
            default="- shared bullet, as the default branch rewrote it\n",
            run="- shared bullet, as the run rewrote it\n",
        )


def test_only_a_declared_path_is_merged(tmp_path: Path) -> None:
    """The declaration is the whole allowlist, read from the committed JSONC.

    The positive and negative halves are one case because either alone is
    satisfied by the wrong reader: a reader that returned every path would pass
    the positive half, and one that returned none would pass the negative.
    """
    program = _materialized(tmp_path=tmp_path)

    declared = program.declared_record_files(text=_DECLARATION)

    assert sorted(declared) == ["notes.md", "record.json"]
    assert declared["record.json"] == _JSON_ENTRY
    assert "SPECIFICATION/contracts.md" not in declared


def test_an_absent_declaration_declares_no_record_files(tmp_path: Path) -> None:
    """ "An absent key declares no record files" — so the arm never fires.

    An adopter repository carries no `record_files` key at all, and the program
    is materialized into every sandbox regardless. Reading the absence as "merge
    anything" is the failure mode that would make this arm unsafe for every
    repository that never opted into it.
    """
    program = _materialized(tmp_path=tmp_path)

    assert program.declared_record_files(text='{"livespec-orchestrator-beads-fabro": {}}') == {}


def test_a_path_escaping_the_repository_is_refused(tmp_path: Path) -> None:
    """A declared path is repository-relative, so a traversal is not a declaration.

    The merger writes the file it merges. A declaration naming `../` or an
    absolute path would therefore make the arm a write primitive outside the
    clone, which is a property of the DECLARATION rather than of any conflict, so
    no behavioural case can reach it.
    """
    program = _materialized(tmp_path=tmp_path)
    escaping = '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": ['
    escaping += '{"path": "../outside.json", "format": "json-array", "key": ["id"]}]}}}'

    with pytest.raises(program.RecordFileMergeUnresolvable):
        _ = program.declared_record_files(text=escaping)


def test_an_unknown_declared_format_is_refused(tmp_path: Path) -> None:
    """Only the two ratified formats resolve; a third is handed back, not guessed."""
    program = _materialized(tmp_path=tmp_path)

    with pytest.raises(program.RecordFileMergeUnresolvable):
        _ = program.merged_record(
            entry={"path": "record.json", "format": "yaml-array"},
            base="",
            default="",
            run="",
        )


def test_the_program_carries_no_import_of_this_package(tmp_path: Path) -> None:
    """The governed clone has no copy of this package, so the program may not need one.

    Asserted on the source bytes rather than by importing in a clean process,
    because an import of a package that HAPPENS to be installed where the suite
    runs would succeed here and fail only in the sandbox, after a conflict.
    """
    _ = tmp_path

    assert "livespec_orchestrator_beads_fabro" not in record_file_merge_program_source()


def test_the_prepare_step_lands_the_program_where_the_stage_resolves_it() -> None:
    """One root, spelled once: the stage reads the path the prepare step wrote.

    A node resolving a DIFFERENT root than the prepare pass would find no program
    at all, and the refresh would then route every record-file conflict to repair
    while reporting the merger absent — a failure that reads as a Dispatcher that
    never materialized one.
    """
    assert _MODULE_PATH.is_file()
    block = record_file_merge_program_prepare_steps_block()
    expansion = record_file_merge_program_path_expansion()

    assert expansion.endswith(f"/{RECORD_FILE_MERGE_PROGRAM_FILENAME}")
    assert "[[run.prepare.steps]]" in block
    assert json.dumps(record_file_merge_program_source()).strip('"') in block
    assert RECORD_FILE_MERGE_PROGRAM_FILENAME in block
