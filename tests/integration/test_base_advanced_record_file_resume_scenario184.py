"""Scenario 184's declared-record-file arm for an overtaken armed pull request.

The Dispatcher may resume only when its read-only merge measurement reports a
non-empty conflict set confined to paths declared in ``dispatcher.record_files``.
The classifier is deliberately exercised apart from the merge command so a
configuration reader that silently treats an undeclared path as declared cannot
make the automatic-resume gate look safe.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record_files"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_base_advance_record_files.py"
)


def _module() -> Any:
    return importlib.import_module(_MODULE)


def test_only_declared_record_file_conflicts_admit_the_resume_arm() -> None:
    """A non-empty all-declared set is distinct from absent and mixed sets."""
    assert _MODULE_PATH.is_file()
    module = _module()
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

    assert module.record_file_resume_paths(
        config_text=declaration,
        conflicted_paths=("tests/heading-coverage.json", "SPECIFICATION/scenarios.md"),
    ) == ("tests/heading-coverage.json", "SPECIFICATION/scenarios.md")
    assert (
        module.record_file_resume_paths(
            config_text=declaration,
            conflicted_paths=("tests/heading-coverage.json", "app.py"),
        )
        is None
    )
    assert module.record_file_resume_paths(config_text=declaration, conflicted_paths=()) is None
