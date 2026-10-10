"""Scenario 112 — the one-shot plan-record migration, run twice.

Binds `SPECIFICATION/scenarios.md` "Scenario 112 — The one-shot anchor
migration is complete and idempotent" and the `SPECIFICATION/contracts.md`
plan-record conformance clauses that require it to run once per family tenant
before the error-verdict checks arm there.

The whole command runs as production code — the argv parse, the connection
resolution off the repository's own `.livespec.jsonc`, the tenant read, every
slug/anchor/pointer decision, both ledger writes through the existing store
bridge, the on-disk anchor writes, and the rendered report — against the REAL
store/client seam over a tenant built through the client's public write verbs.
The entry point is invoked exactly as an operator invokes it, argv and all.

The fixture carries every shape the contract distinguishes, because a migration
that handled only the easy one would still report a plausible non-empty run: an
epic already carrying a slug, an untagged epic whose `plan:<slug>` commitment
hint supplies one, an untagged epic whose title collides with a slug another
epic already carries (refused, not renamed), a CLOSED epic under
`plan/archive/`, a live plan directory no epic claims (anchored `unassigned`),
a legacy handoff naming a work-item (seeded `kind: impl`) and an epic with no
handoff at all (seeded `kind: none`).

IDEMPOTENCE IS ASSERTED ON THREE INSTRUMENTS, not one, because each alone has a
way to read clean while work was redone. The report's write count says the
second run DECIDED to write nothing; the anchor bytes say the filesystem was
not rewritten; and the full record dump says no ledger row moved — including
`last_session`, which a re-seed would restamp with a fresh timestamp while
every other field stayed identical. The refusal is deliberately still reported
on the second run: a refusal is a result rather than a write, so it recurs
while the write count stays zero.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands.migrate_plan_records import main
from livespec_orchestrator_beads_fabro.commands.plan import PLAN_HANDOFF_PREFIX
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    from collections.abc import Sequence

_NOW = "2026-09-05T12:00:00Z"
_ANCHOR_FILENAME = "associated_work_item_id"
_ALPHA = "bd-ib-s112alpha"
_COLLIDES = "bd-ib-s112collides"
_GAMMA = "bd-ib-s112gamma"
_HOLDER = "bd-ib-s112holder"
_KAPPA = "bd-ib-s112kappa"
# The plan directories the fixture repository holds: three live ones (`beta`
# claimed by no epic) and one archived.
_LIVE_SLUGS = ("alpha", "beta", "kappa")
_ARCHIVED_SLUG = "gamma"


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _client() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _seed_epic(
    *,
    epic_id: str,
    title: str,
    plan_slug: str | None = None,
    spec_id: str | None = None,
    closed: bool = False,
) -> None:
    metadata: dict[str, Any] = {"rank": "a1"}
    if plan_slug is not None:
        metadata["plan_slug"] = plan_slug
    client = _client()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=epic_id,
            issue_type="epic",
            title=title,
            description=f"{epic_id} description",
            assignee=None,
            created_at="2026-09-01T00:00:00Z",
            metadata=metadata,
            labels=["origin:freeform"],
            spec_id=spec_id,
        )
    )
    if closed:
        client.close_issue(issue_id=epic_id, reason="plan archived")


def _seed_legacy_handoff(*, epic_id: str, body: str) -> None:
    """Seed the pre-migration handoff shape: a comment carrying no typed pointer."""
    _client().seed_comment(
        issue_id=epic_id,
        text=f"{PLAN_HANDOFF_PREFIX}\nauthor: console\ntimestamp: {_NOW}\n\n{body}",
        author="console",
        created_at=_NOW,
    )


def _fixture_repository(*, project_root: Path) -> None:
    _seed_epic(epic_id=_ALPHA, title="Alpha plan", plan_slug="alpha")
    _seed_epic(epic_id=_GAMMA, title="Gamma plan", plan_slug="gamma", closed=True)
    _seed_epic(epic_id=_HOLDER, title="Shared topic", plan_slug="shared-topic")
    _seed_epic(epic_id=_COLLIDES, title="Shared Topic!")
    _seed_epic(epic_id=_KAPPA, title="Anything at all", spec_id="plan:kappa")
    _seed_legacy_handoff(epic_id=_ALPHA, body="Next action: run impl:bd-ib-ott6 in the factory\n")
    _ = (project_root / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    for slug in _LIVE_SLUGS:
        (project_root / "plan" / slug).mkdir(parents=True)
    (project_root / "plan" / "archive" / _ARCHIVED_SLUG).mkdir(parents=True)


def _run(*, project_root: Path, capsys: pytest.CaptureFixture[str]) -> list[str]:
    assert main(argv=["--project-root", str(project_root)]) == 0
    return capsys.readouterr().out.splitlines()


def _anchor_paths(*, project_root: Path) -> list[Path]:
    live = [project_root / "plan" / slug / _ANCHOR_FILENAME for slug in _LIVE_SLUGS]
    return [*live, project_root / "plan" / "archive" / _ARCHIVED_SLUG / _ANCHOR_FILENAME]


def _anchors(*, project_root: Path) -> dict[str, str]:
    return {
        path.relative_to(project_root).as_posix(): path.read_text(encoding="utf-8")
        for path in _anchor_paths(project_root=project_root)
    }


def _records() -> str:
    return json.dumps(_client().list_issues(), sort_keys=True)


def _written(*, lines: Sequence[str]) -> list[str]:
    return [line for line in lines if line.startswith("wrote: ")]


def test_scenario112_the_first_run_writes_every_missing_slug_anchor_and_pointer(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _fixture_repository(project_root=tmp_path)

    lines = _run(project_root=tmp_path, capsys=capsys)

    assert lines == [
        "migrate-plan-records: 7 write(s)",
        f"wrote: {_KAPPA} plan_slug=kappa",
        f"wrote: plan/alpha/{_ANCHOR_FILENAME} -> {_ALPHA}",
        f"wrote: plan/beta/{_ANCHOR_FILENAME} -> unassigned",
        f"wrote: plan/kappa/{_ANCHOR_FILENAME} -> {_KAPPA}",
        f"wrote: plan/archive/gamma/{_ANCHOR_FILENAME} -> {_GAMMA}",
        f"wrote: {_ALPHA} kind=human ref='bd-ib-ott6'",
        f"wrote: {_KAPPA} kind=none ref=''",
        f"skipped: {_ALPHA} already carries plan_slug=alpha",
        f"skipped: {_GAMMA} already carries plan_slug=gamma",
        f"skipped: {_HOLDER} already carries plan_slug=shared-topic",
        f"refused: {_COLLIDES} derives plan_slug=shared-topic, already carried by {_HOLDER}",
    ]
    assert _anchors(project_root=tmp_path) == {
        f"plan/alpha/{_ANCHOR_FILENAME}": f"{_ALPHA}\n",
        f"plan/beta/{_ANCHOR_FILENAME}": "unassigned\n",
        f"plan/kappa/{_ANCHOR_FILENAME}": f"{_KAPPA}\n",
        f"plan/archive/gamma/{_ANCHOR_FILENAME}": f"{_GAMMA}\n",
    }
    # The colliding epic is reported and LEFT UNWRITTEN, never renamed.
    assert "plan_slug" not in _client().show_issue(issue_id=_COLLIDES)["metadata"]
    assert _client().show_issue(issue_id=_ALPHA)["metadata"]["next_action"] == {
        "kind": "human",
        "ref": "bd-ib-ott6",
        "text": "Confirm required-result tracking and budget before dispatching bd-ib-ott6.",
        "required_result": None,
        "budget": None,
    }


def test_scenario112_a_second_run_writes_nothing_and_leaves_every_record_identical(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _fixture_repository(project_root=tmp_path)

    first = _run(project_root=tmp_path, capsys=capsys)
    anchors_after_first = _anchors(project_root=tmp_path)
    records_after_first = _records()

    second = _run(project_root=tmp_path, capsys=capsys)

    assert len(_written(lines=first)) == 7
    assert second == [
        "migrate-plan-records: 0 write(s)",
        f"skipped: {_ALPHA} already carries plan_slug=alpha",
        f"skipped: {_GAMMA} already carries plan_slug=gamma",
        f"skipped: {_HOLDER} already carries plan_slug=shared-topic",
        f"skipped: {_KAPPA} already carries plan_slug=kappa",
        f"skipped: plan/alpha/{_ANCHOR_FILENAME} already anchored",
        f"skipped: plan/beta/{_ANCHOR_FILENAME} already anchored",
        f"skipped: plan/kappa/{_ANCHOR_FILENAME} already anchored",
        f"skipped: plan/archive/gamma/{_ANCHOR_FILENAME} already anchored",
        f"skipped: {_ALPHA} already carries next_action",
        f"skipped: {_KAPPA} already carries next_action",
        f"refused: {_COLLIDES} derives plan_slug=shared-topic, already carried by {_HOLDER}",
    ]
    assert _written(lines=second) == []
    assert _anchors(project_root=tmp_path) == anchors_after_first
    assert _records() == records_after_first
