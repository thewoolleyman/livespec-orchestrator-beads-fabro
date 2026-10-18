"""The durable record a successful tree preservation leaves on the item."""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    PreservedTree,
)

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = f"{_PACKAGE}._dispatcher_preserved_tree_record"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_preserved_tree_record.py"
)

_RUN_ID = "01M4YJGC55V86C9V1X07QG3Y2H"
_FACTORY = "hp"
_COMMIT = "c0mm1tc0mm1tc0mm1tc0mm1tc0mm1tc0mm1tc0mm"
_REF = f"refs/livespec/preserved-publish/bd-ib-na2xvm/{_COMMIT}"
_BASE_COMMIT = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_a_successful_preservation_names_the_run_the_factory_the_ref_and_its_commit() -> None:
    # The module does not exist at Red, so this is a genuine assertion failure
    # rather than a collection error.
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    record = importlib.import_module(_MODULE)
    body = record.preserved_tree_body(
        work_item_id="bd-ib-na2xvm",
        run_id=_RUN_ID,
        factory=_FACTORY,
        base_commit=_BASE_COMMIT,
        preserved=PreservedTree(
            ref=_REF, commit=_COMMIT, file_count=3, scope="committed", source="sandbox"
        ),
    )
    assert body.splitlines()[0] == "livespec-preserved-tree"
    assert record.PRESERVED_TREE_MARKER == "livespec-preserved-tree"
    for named in (_RUN_ID, _FACTORY, _REF, _COMMIT, _BASE_COMMIT, "bd-ib-na2xvm", "3"):
        assert named in body, named
    # The comment is append-only and cannot be repaired, so it must carry no
    # opener that would refuse every later dispatch of this item.
    assert minijinja_openers_in_text(source="preserved-tree", text=body) == ()
