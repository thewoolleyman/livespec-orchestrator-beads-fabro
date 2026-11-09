"""The edges of completing a handed-off merge wait that the headline cases cannot reach.

Sits beside `test_dispatcher_stranded_claim_handoff.py` for the reason a Red's test
bytes are fixed across its Red-to-Green pair: each arm here was found by a coverage
measurement taken after that module's Red was authored.

THE JOURNAL READ AND THE FORGE READ FAIL CLOSED. A handoff row is trusted only when
it sits in the newest dispatch's segment, names the claim's own run and carries a
real pull request number; a forge answer is trusted only when it is one of the
states the reading recognises and the required-check list could be read. Every
other shape holds the claim, and the hold is the cheap ending: the next pass reads
again, while a wrong completion asks a person to act on a guess or runs the
janitor on an unmerged tree.

THE RECOVERY'S REFUSALS ARE HOLDS, NEVER RECOVERIES. A lock that cannot be taken, a
row that cannot be read, a claim another writer changed and a disposition the
claim-token protocol refused each leave the item exactly as found.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimRow,
    ClaimStamp,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_stranded_claim_handoff_recovery as recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_handoff import (
    handed_off_pull_request,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey import (
    FactoryInventory,
    StrandedClaimInputs,
    survey_stranded_claims,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_terminal import (
    RefusedDisposition,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-handoffedge"
_RUN_ID = "01EDGERUN"
_HOST = "owning-host"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_PR = 4615
_LAUNCH = {"stage": "dispatch-id", "work_item_id": _ITEM_ID}


def _handoff(
    *, number: object = _PR, run_id: str = _RUN_ID, item: str = _ITEM_ID
) -> dict[str, Any]:
    return {
        "stage": "merge-wait-handed-off",
        "work_item_id": item,
        "run_id": run_id,
        "pr_number": number,
    }


@pytest.mark.parametrize(
    ("records", "expected"),
    [
        (None, None),
        ((), None),
        ((_handoff(),), None),
        ((_LAUNCH, _handoff()), _PR),
        ((_LAUNCH, _handoff(number=True)), None),
        ((_LAUNCH, _handoff(number="4615")), None),
        ((_LAUNCH, _handoff(run_id="01OTHER")), None),
        ((_LAUNCH, _handoff(item="bd-ib-other")), None),
        ((_handoff(), _LAUNCH), None),
        ((_LAUNCH, _handoff(number=7), _handoff(number=8)), 8),
        (
            (_LAUNCH, _handoff(number=7), {"stage": "dispatch-id", "work_item_id": "bd-ib-other"}),
            7,
        ),
    ],
    ids=[
        "journal-unreadable",
        "empty-journal",
        "no-dispatch-opening",
        "handed-off",
        "boolean-number",
        "string-number",
        "other-run",
        "other-item",
        "earlier-dispatch",
        "newest-row-wins",
        "another-items-dispatch-does-not-close-the-segment",
    ],
)
def test_a_handoff_row_is_trusted_only_in_the_claims_own_newest_segment(
    records: tuple[dict[str, Any], ...] | None, expected: int | None
) -> None:
    assert (
        handed_off_pull_request(records=records, work_item_id=_ITEM_ID, run_id=_RUN_ID) == expected
    )


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
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


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A handed-off slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _stamp() -> ClaimStamp:
    return ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host=_HOST,
        run_id=_RUN_ID,
        factory_name=_FACTORY,
        factory_server=_SERVER,
    )


def _view(*, state: str = "OPEN", armed: bool = True) -> str:
    return json.dumps(
        {
            "number": _PR,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"} if armed else None,
            "mergeStateStatus": "BLOCKED",
            "mergeCommit": {"oid": "cafe05"} if state == "MERGED" else None,
            "headRefOid": "head1111",
            "baseRefOid": "base2222",
            "statusCheckRollup": [],
        }
    )


class _Forge:
    def __init__(self, *, view: CommandResult, graphql: CommandResult) -> None:
        self.view = view
        self.graphql = graphql
        self.argvs: list[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        if argv[:3] == ["gh", "pr", "view"]:
            return self.view
        return self.graphql


_NO_REQUIRED = json.dumps(
    {
        "data": {
            "repository": {
                "pullRequest": {
                    "commits": {
                        "nodes": [{"commit": {"statusCheckRollup": {"contexts": {"nodes": []}}}}]
                    }
                }
            }
        }
    }
)


def _ok(*, stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_LAUNCH, _handoff()]
    _ = path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return JournalFile(path=path)


def _survey(
    *, repo: Path, journal: JournalFile, forge: _Forge, dry_run: bool = False
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    append_work_item(path=_config(), item=_item())
    record_claim_stamp(path=_config(), work_item_id=_ITEM_ID, stamp=_stamp())
    survey = survey_stranded_claims(
        inputs=StrandedClaimInputs(
            repo=repo,
            items=(_item(),),
            journal=journal,
            runner=forge,
            inventories=(
                FactoryInventory(
                    name=_FACTORY,
                    server_url=_SERVER,
                    fabro_bin="fabro",
                    surveyed=True,
                    status_kinds={_RUN_ID: "succeeded"},
                ),
            ),
            this_host=_HOST,
            now_iso="2026-11-08T09:00:00Z",
            dry_run=dry_run,
        )
    )
    return survey.recovered, survey.held


def _stored() -> WorkItem:
    return next(iter(read_work_items(path=_config())))


@pytest.mark.parametrize(
    ("view", "graphql"),
    [
        (_ok(stdout=_view(state="UNKNOWN")), _ok(stdout=_NO_REQUIRED)),
        (_ok(stdout=_view()), CommandResult(exit_code=1, stdout="", stderr="graphql failed")),
        (_ok(stdout=_view()), _ok(stdout="not json")),
    ],
    ids=["unrecognised-state", "required-checks-unreadable", "required-checks-garbled"],
)
def test_a_forge_answer_the_reading_cannot_trust_holds_the_claim(
    tmp_path: Path, view: CommandResult, graphql: CommandResult
) -> None:
    repo = _repo(tmp_path=tmp_path)

    recovered, held = _survey(
        repo=repo, journal=_journal(repo=repo), forge=_Forge(view=view, graphql=graphql)
    )

    assert recovered == ()
    assert [h.hold_reason for h in held] == ["run-succeeded"]
    assert "could not be read" in (held[0].detail or "")
    assert _stored().status == "active"


def test_a_dry_pass_projects_the_route_and_changes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    before = journal.path.read_text(encoding="utf-8")
    forge = _Forge(view=_ok(stdout=_view(state="CLOSED", armed=False)), graphql=_ok(stdout=""))

    recovered, held = _survey(repo=repo, journal=journal, forge=forge, dry_run=True)

    assert held == ()
    assert [(r.route, r.status, r.effects_written) for r in recovered] == [
        ("merge-wait-handoff-rest", "active", ())
    ]
    assert _stored().status == "active"
    assert journal.path.read_text(encoding="utf-8").startswith(before)


def _closed_forge() -> _Forge:
    return _Forge(view=_ok(stdout=_view(state="CLOSED", armed=False)), graphql=_ok(stdout=""))


def test_a_lock_that_cannot_be_taken_holds_the_claim_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def _no_fence(**_: object) -> Iterator[bool]:
        yield False

    monkeypatch.setattr(recovery, "claim_recovery_fence", _no_fence)
    repo = _repo(tmp_path=tmp_path)

    recovered, held = _survey(repo=repo, journal=_journal(repo=repo), forge=_closed_forge())

    assert recovered == ()
    assert [h.hold_reason for h in held] == ["effect-unobservable"]
    assert _stored().status == "active"


def test_a_row_that_cannot_be_read_holds_the_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recovery, "claim_row", lambda **_: None)
    repo = _repo(tmp_path=tmp_path)

    recovered, held = _survey(repo=repo, journal=_journal(repo=repo), forge=_closed_forge())

    assert recovered == ()
    assert [h.hold_reason for h in held] == ["effect-unobservable"]


def test_a_claim_another_writer_changed_is_held_as_claim_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changed = ClaimRow(status="active", assignee="fabro", stamp=None)
    monkeypatch.setattr(recovery, "claim_row", lambda **_: changed)
    repo = _repo(tmp_path=tmp_path)

    recovered, held = _survey(repo=repo, journal=_journal(repo=repo), forge=_closed_forge())

    assert recovered == ()
    assert [h.hold_reason for h in held] == ["claim-changed"]
    assert _stored().status == "active"


@pytest.mark.parametrize(
    ("refusal", "reason"),
    [("claim-changed", "claim-changed"), ("claim-lease-expired", "effect-unobservable")],
)
def test_a_disposition_the_claim_token_protocol_refused_is_a_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal: str, reason: str
) -> None:
    monkeypatch.setattr(
        recovery, "apply_terminal_disposition", lambda **_: RefusedDisposition(outcome=refusal)
    )
    repo = _repo(tmp_path=tmp_path)

    recovered, held = _survey(repo=repo, journal=_journal(repo=repo), forge=_closed_forge())

    assert recovered == ()
    assert [h.hold_reason for h in held] == [reason]


def test_a_reconcile_that_leaves_no_readable_row_still_reports_the_claim_recovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads: list[int] = []

    def _row(**_: object) -> ClaimRow | None:
        reads.append(1)
        return (
            ClaimRow(status="active", assignee="fabro", stamp=_stamp()) if len(reads) < 3 else None
        )

    monkeypatch.setattr(recovery, "claim_row", _row)
    monkeypatch.setattr(recovery, "reconcile_merged_for_claim", lambda **_: 0)
    repo = _repo(tmp_path=tmp_path)
    forge = _Forge(view=_ok(stdout=_view(state="MERGED", armed=False)), graphql=_ok(stdout=""))

    recovered, held = _survey(repo=repo, journal=_journal(repo=repo), forge=forge)

    assert held == ()
    assert [(r.route, r.status) for r in recovered] == [
        ("merge-wait-handoff-reconcile-merged", "active")
    ]


def test_the_reconcile_is_driven_with_the_passes_own_journal_and_the_fence_forced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[argparse.Namespace] = []

    def _reconcile(*, args: argparse.Namespace) -> int:
        seen.append(args)
        return 0

    monkeypatch.setattr(recovery, "reconcile_merged_for_claim", _reconcile)
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    forge = _Forge(view=_ok(stdout=_view(state="MERGED", armed=False)), graphql=_ok(stdout=""))

    _survey(repo=repo, journal=journal, forge=forge)

    assert len(seen) == 1
    assert seen[0].journal == str(journal.path)
    assert (seen[0].force, seen[0].regrade, seen[0].janitor, seen[0].as_json) == (
        True,
        False,
        None,
        False,
    )
    assert seen[0].invoker in {None, journal.identity.invoker}


def test_the_default_reconcile_drives_the_valves_own_command_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_merged as valve

    seen: list[argparse.Namespace] = []

    def _command(*, args: argparse.Namespace, runner: object = None) -> int:
        _ = runner
        seen.append(args)
        return 7

    monkeypatch.setattr(valve, "run_reconcile_merged_command", _command)
    args = argparse.Namespace(item=_ITEM_ID)

    assert recovery.reconcile_merged_for_claim(args=args) == 7
    assert seen == [args]
