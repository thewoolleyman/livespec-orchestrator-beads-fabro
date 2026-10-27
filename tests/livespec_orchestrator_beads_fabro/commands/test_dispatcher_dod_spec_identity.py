"""The clause identity is stable only while its selected clauses are stable."""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = (
    Path(__file__).parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_dispatcher_dod_spec_identity.py"
)
_GOVERNING = "## Scenario 206 — The clause that governs this assertion"


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-onrjh3",
        type="feature",
        status="ready",
        title="Clause identity",
        description="## Definition of Done\n\n- The governed assertion.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-27T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _module() -> ModuleType:
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity"
    )


def _repo(*, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    specification = root / "SPECIFICATION"
    specification.mkdir(parents=True)
    _ = (specification / "clauses.md").write_text(
        f"# Clauses\n\n{_GOVERNING}\n\nThe original clause body.\n",
        encoding="utf-8",
    )
    return root


def test_clause_identity_ignores_an_unrelated_revision_but_tracks_the_clause_body(
    tmp_path: Path,
) -> None:
    """A host taking is reusable only while the assertion's clause bytes match."""
    assert _MODULE_PATH.is_file()
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    governing = GoverningHeadingVerdict(kind="stated", stated_by=(_GOVERNING,))

    original = module.spec_identity_for_governing(item=_item(), cwd=repo, governing=governing)
    _ = (repo / "SPECIFICATION" / "unrelated.md").write_text(
        "# Unrelated\n\n## Scenario 999 — Other clause\n\nOther body.\n", encoding="utf-8"
    )
    unrelated = module.spec_identity_for_governing(item=_item(), cwd=repo, governing=governing)
    _ = (repo / "SPECIFICATION" / "clauses.md").write_text(
        f"# Clauses\n\n{_GOVERNING}\n\nThe changed clause body.\n", encoding="utf-8"
    )
    changed = module.spec_identity_for_governing(item=_item(), cwd=repo, governing=governing)

    assert original.form == "clauses"
    assert original.value == unrelated.value
    assert changed.value != original.value
    assert original.provenance[0].path == "clauses.md"
    assert original.provenance[0].heading == _GOVERNING.removeprefix("## ")


def test_clause_identity_falls_back_to_the_tree_when_provenance_cannot_be_resolved(
    tmp_path: Path,
) -> None:
    """No governing verdict or unreadable clause provenance cannot reuse clauses."""
    assert _MODULE_PATH.is_file()
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    missing = GoverningHeadingVerdict(kind="stated", stated_by=("## Missing",))

    absent = module.spec_identity_for_governing(item=_item(), cwd=repo, governing=None)
    unresolved = module.spec_identity_for_governing(item=_item(), cwd=repo, governing=missing)
    no_tree = module.spec_identity_for_governing(
        item=_item(), cwd=tmp_path / "missing", governing=missing
    )

    assert absent.form == "tree"
    assert unresolved.form == "tree"
    assert no_tree.value == "tree:unreadable"


def test_clause_identity_falls_back_when_a_clause_file_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clause whose bytes cannot be read is not a stable subject identity."""
    assert _MODULE_PATH.is_file()
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    clause = repo / "SPECIFICATION" / "clauses.md"
    _ = (repo / "SPECIFICATION" / "before.md").write_text("# Before\n", encoding="utf-8")
    original_read_text = Path.read_text

    def unreadable(path: Path, *args: object, **kwargs: object) -> str:
        if path == clause:
            raise OSError("denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)

    identity = module.spec_identity_for_governing(
        item=_item(),
        cwd=repo,
        governing=GoverningHeadingVerdict(kind="stated", stated_by=(_GOVERNING,)),
    )

    assert identity.form == "tree"


def test_clause_identity_falls_back_for_empty_assertions_and_duplicate_selection(
    tmp_path: Path,
) -> None:
    """Neither a criterion-free item nor duplicate verdict address is complete provenance."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    stated = GoverningHeadingVerdict(kind="stated", stated_by=(_GOVERNING,))

    empty = module.spec_identity_for_governing(
        item=replace(_item(), description="No Definition of Done assertions."),
        cwd=repo,
        governing=stated,
    )
    duplicate = module.spec_identity_for_governing(
        item=_item(),
        cwd=repo,
        governing=GoverningHeadingVerdict(kind="stated", stated_by=(_GOVERNING, _GOVERNING)),
    )

    assert empty.form == duplicate.form == "tree"


def test_subject_digest_for_governing_uses_the_selected_identity(tmp_path: Path) -> None:
    """The public helper carries clause form into the reusable judgement subject."""
    module = _module()

    digest = module.subject_digest_for_governing(
        item=_item(),
        cwd=_repo(tmp_path=tmp_path),
        comments=(),
        governing=GoverningHeadingVerdict(kind="stated", stated_by=(_GOVERNING,)),
    )

    assert len(digest) == 64


def test_clause_identity_falls_back_when_the_verdict_does_not_cover_every_assertion(
    tmp_path: Path,
) -> None:
    """Only a fully stated governing verdict may select the clause form."""
    module = _module()
    identity = module.spec_identity_for_governing(
        item=_item(),
        cwd=_repo(tmp_path=tmp_path),
        governing=GoverningHeadingVerdict(kind="partial", stated_by=(_GOVERNING,)),
    )

    assert identity.form == "tree"
    assert identity.value.startswith("tree:")


def test_clause_identity_falls_back_when_a_selected_heading_is_ambiguous(tmp_path: Path) -> None:
    """A repeated H2 title cannot be reduced to whichever clause appears last."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    _ = (repo / "SPECIFICATION" / "second.md").write_text(
        f"# More clauses\n\n{_GOVERNING}\n\nA different body.\n", encoding="utf-8"
    )

    identity = module.spec_identity_for_governing(
        item=_item(),
        cwd=repo,
        governing=GoverningHeadingVerdict(kind="stated", stated_by=(_GOVERNING,)),
    )

    assert identity.form == "tree"


def test_clause_identity_binds_each_assertion_and_each_clause_list() -> None:
    """The digest's framing cannot confuse changed assertion or clause inputs."""
    assert _MODULE_PATH.is_file()
    module = _module()
    clause = module.ClauseProvenance(path="clauses.md", heading="Scenario", body=b"body")

    one = module.clause_spec_identity(assertions=("first",), clauses=(clause,))
    changed_assertion = module.clause_spec_identity(assertions=("second",), clauses=(clause,))
    changed_clause = module.clause_spec_identity(
        assertions=("first",),
        clauses=(module.ClauseProvenance(path="clauses.md", heading="Scenario", body=b"new"),),
    )

    assert one.value != changed_assertion.value
    assert one.value != changed_clause.value
