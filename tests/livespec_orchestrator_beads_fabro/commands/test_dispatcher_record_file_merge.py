"""The declared-record-file merge program used by refresh stages."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_COMMANDS = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_MODULE_PATH = _COMMANDS / "_dispatcher_record_file_merge.py"


def _module() -> ModuleType:
    """Load the materialized program after a genuine Red existence assertion."""
    assert _MODULE_PATH.is_file()
    spec = importlib.util.spec_from_file_location("record_file_merge", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_record_files_merge_by_declared_format_and_refuse_unsafe_inputs(
    tmp_path: Path,
) -> None:
    """Scenario 200 keeps independent entries and declines ambiguous edits."""
    module = _module()
    program = module.record_file_merge_program_source()
    program_path = tmp_path / "livespec-record-file-merge.py"
    _ = program_path.write_text(program, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("record_file_merge_program", program_path)
    assert spec is not None
    assert spec.loader is not None
    materialized = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(materialized)
    merge = materialized.merged_record
    refusal = materialized.RecordFileMergeUnresolvable

    merged, default_count, run_count = merge(
        entry={"path": "record.json", "format": "json-array", "key": ["id"]},
        base='[{"id": "shared"}]\n',
        default='[{"id": "shared"}, {"id": "default"}]\n',
        run='[{"id": "shared"}, {"id": "run"}]\n',
    )
    assert json.loads(merged) == [
        {"id": "shared"},
        {"id": "default"},
        {"id": "run"},
    ]
    assert (default_count, run_count) == (2, 1)

    merged, default_count, run_count = merge(
        entry={"path": "notes.md", "format": "markdown-insertions"},
        base="- base\n",
        default="- base\n- default\n",
        run="- base\n- run\n",
    )
    assert merged == "- base\n- default\n- run\n"
    assert (default_count, run_count) == (1, 1)

    with pytest.raises(refusal):
        merge(
            entry={"path": "record.json", "format": "json-array", "key": ["id"]},
            base='[{"id": "shared", "value": "base"}]\n',
            default='[{"id": "shared", "value": "default"}]\n',
            run='[{"id": "shared", "value": "run"}]\n',
        )


def test_the_merge_program_is_materialized_by_the_plugin_prepare_block() -> None:
    """A refresh resolves the same path the prepare pass writes."""
    module = _module()

    assert module.RECORD_FILE_MERGE_PROGRAM_FILENAME == "livespec-record-file-merge.py"
    assert module.record_file_merge_program_path_expansion().endswith(
        module.RECORD_FILE_MERGE_PROGRAM_FILENAME
    )
    assert module.record_file_merge_program_source() in (
        module.record_file_merge_program_prepare_steps_block()
    )
