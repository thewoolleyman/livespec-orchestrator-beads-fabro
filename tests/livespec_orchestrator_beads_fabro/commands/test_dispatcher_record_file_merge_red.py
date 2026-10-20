"""The first red assertion for declared record-file refresh merging."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import Protocol, cast

_MODULE_PATH = (
    Path(__file__).parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_record_file_merge.py"
)


class _SourceModule(Protocol):
    """The public source renderer exercised by this red/green test."""

    def record_file_merge_program_source(self) -> str:
        """Render the sandbox-only record-file merge helper."""


class _MaterializedProgram(Protocol):
    """The narrow surface this test needs from the materialized program."""

    def merged_record(
        self,
        *,
        entry: dict[str, object],
        base: str,
        default: str,
        run: str,
    ) -> tuple[str, int, int]:
        """Merge one declared record-file conflict."""


def _materialized_program(*, temporary_directory: Path) -> _MaterializedProgram:
    """Load the generated program exactly as the sandbox prepare step does."""
    assert _MODULE_PATH.is_file()
    source_module = cast(
        _SourceModule,
        importlib.import_module(
            "livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge"
        ),
    )
    program_path = temporary_directory / "livespec-record-file-merge.py"
    program_path.write_text(source_module.record_file_merge_program_source())
    specification = importlib.util.spec_from_file_location(
        "record_file_merge_program", program_path
    )
    assert specification is not None
    assert specification.loader is not None
    program = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(program)
    return cast(_MaterializedProgram, program)


def test_declared_json_records_keep_default_order_then_run_additions(
    tmp_path: Path,
) -> None:
    """A record conflict keeps the default side first and appends this run."""
    program = _materialized_program(temporary_directory=tmp_path)
    declaration = {
        "path": "tests/heading-coverage.json",
        "format": "json-array",
        "key": ["spec_root", "spec_file", "heading"],
    }
    base = '[{"spec_root":"spec","spec_file":"a.md","heading":"A"}]\n'
    default = (
        '[{"spec_root":"spec","spec_file":"a.md","heading":"A"},'
        '{"spec_root":"spec","spec_file":"b.md","heading":"B"}]\n'
    )
    run = (
        '[{"spec_root":"spec","spec_file":"a.md","heading":"A"},'
        '{"spec_root":"spec","spec_file":"c.md","heading":"C"}]\n'
    )

    merged, default_count, run_count = program.merged_record(
        entry=declaration,
        base=base,
        default=default,
        run=run,
    )

    assert merged == (
        "[\n"
        "  {\n"
        '    "spec_root": "spec",\n'
        '    "spec_file": "a.md",\n'
        '    "heading": "A"\n'
        "  },\n"
        "  {\n"
        '    "spec_root": "spec",\n'
        '    "spec_file": "b.md",\n'
        '    "heading": "B"\n'
        "  },\n"
        "  {\n"
        '    "spec_root": "spec",\n'
        '    "spec_file": "c.md",\n'
        '    "heading": "C"\n'
        "  }\n"
        "]\n"
    )
    assert (default_count, run_count) == (2, 1)
