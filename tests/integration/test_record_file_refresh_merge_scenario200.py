"""Scenario 200 — declared record files merge during a refresh, without a repair round.

WHY THIS FILE EXISTS. `SPECIFICATION/contracts.md` section "Declared record
files merge without a repair round" (revision v162) gives the refresh stages a
new arm: a conflict confined to files this repository DECLARES as shared
append-only records is merged entry by entry rather than handed to the fix
agent. The declaration is the whole input to that arm, and it lives in committed
configuration rather than in code, so nothing in the package can establish it.

The five STAGE sub-scenarios are exercised against the shipped `pr_refresh`
bytes in `test_scripted_refresh_execution.py`, beside that module's real-Git
harness; the merge arm is a property of the stage script, and restating that
harness here would grade a paraphrase of it.

The declaration case below is therefore a CONFIGURATION assertion, graded
against the committed `.livespec.jsonc` exactly as the refresh stage reads it:
the stage runs in a governed clone with no copy of this package, so it opens
that file itself, and a declaration that drifted from the four files this
repository's revise and scenario-binding changes actually append to would leave
the arm armed for paths nothing ever conflicts in — silently, because a refresh
that found no declared path routes to repair exactly as it did before v162.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._jsonc import loads

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The four shared records every revise and every scenario-binding change in this
# repository appends to, and therefore the four this repository declares. The two
# JSON arrays are keyed by the triple that identifies one heading, which is the
# identity `heading_coverage` itself indexes them by; the two Markdown files are
# flat bullet registries a new test file inserts one entry into.
_EXPECTED_RECORD_FILES = [
    {
        "path": "tests/heading-coverage.json",
        "format": "json-array",
        "key": ["spec_root", "spec_file", "heading"],
    },
    {
        "path": "tests/heading-coverage-debt.json",
        "format": "json-array",
        "key": ["spec_root", "spec_file", "heading"],
    },
    {"path": "tests/integration/CLAUDE.md", "format": "markdown-insertions"},
    {"path": "tests/prompts/CLAUDE.md", "format": "markdown-insertions"},
]


def _committed_dispatcher_configuration() -> dict[str, object]:
    """The committed `dispatcher` table, read the way the sandbox stage reads it.

    Through the repository's own JSONC loader rather than `json.loads`, because
    `.livespec.jsonc` carries `//` comments and a bare JSON parse of it raises
    rather than returning a drifted value — which would make this case fail for
    the wrong reason and hide whatever the declaration actually says.
    """
    config = cast(
        "dict[str, object]",
        loads(text=(_REPO_ROOT / ".livespec.jsonc").read_text(encoding="utf-8")),
    )
    plugin = config.get("livespec-orchestrator-beads-fabro")
    assert isinstance(plugin, dict)
    dispatcher = plugin.get("dispatcher")
    assert isinstance(dispatcher, dict)
    return cast("dict[str, object]", dispatcher)


def test_the_committed_configuration_declares_this_repositorys_shared_record_files() -> None:
    """The declaration names the four records, with the formats v162 defines.

    Asserted as a whole list rather than by containment: the arm merges ONLY
    declared paths, so an extra entry widens what a refresh will rewrite without
    a human in the loop, and a missing one leaves the collision this item was
    filed for costing a whole factory run. Both directions matter, and only an
    equality check sees both.
    """
    dispatcher = _committed_dispatcher_configuration()

    assert dispatcher.get("record_files") == _EXPECTED_RECORD_FILES
