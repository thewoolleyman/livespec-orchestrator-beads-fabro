"""Scenario 184's declared-record-file arm for an overtaken armed pull request."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record_files import (
    record_file_resume_paths,
)


def test_only_declared_record_file_conflicts_admit_the_resume_arm() -> None:
    """A non-empty all-declared set is distinct from absent and mixed sets."""
    declaration = """{
      "livespec-orchestrator-beads-fabro": {
        "dispatcher": {
          "record_files": [
            {"path": "tests/heading-coverage.json", "format": "json-array", "key": ["heading"]},
            {"path": "SPECIFICATION/scenarios.md", "format": "markdown-insertions"}
          ]
        }
      }
    }"""

    assert record_file_resume_paths(
        config_text=declaration,
        conflicted_paths=("tests/heading-coverage.json", "SPECIFICATION/scenarios.md"),
    ) == ("tests/heading-coverage.json", "SPECIFICATION/scenarios.md")
    assert (
        record_file_resume_paths(
            config_text=declaration,
            conflicted_paths=("tests/heading-coverage.json", "app.py"),
        )
        is None
    )
    assert record_file_resume_paths(config_text=declaration, conflicted_paths=()) is None
