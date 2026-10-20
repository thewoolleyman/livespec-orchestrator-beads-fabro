"""A plan's OWN obligations name, and are read from, the plan's own repository.

Both halves of `bd-ib-woacnk`, bound through the production `resume_directive`
entry point and the real store seam: the pointer the advance WRITES, and the
obligation the resume READS.

WHY A FOREIGN CARRIER IS THE FIXTURE RATHER THAN A DETAIL. A plan's last
satisfied obligation legitimately names another repository — a carrier child
filed in a sibling tenant under the cross-tenant execution mirror — and the
derived proof, review and archive steps all target the PLAN EPIC, which lives in
the plan's own tenant whatever the previous carrier's repository was. Carrying
the satisfied obligation's repository forward therefore stamps a repository the
epic does not live in, and the next resume reads `bd comments <epic> --json`
against the wrong tenant: `plan-progress-tracking: unobservable`, dispatch
withheld, and the plan locked behind a pointer no sanctioned write can replace
because replacing an unobservable obligation is refused by design.

WHY THE SECOND CASE IS NOT A RESTATEMENT OF THE FIRST. Fixing the WRITE leaves
every plan whose pointer was already poisoned exactly as locked as before, so
the READ has to recognise an obligation that names the plan epic itself and
resolve it against the plan's own tenant. The control that distinguishes "reads
it from the right tenant" from merely "reports something observable" is the
POSITIVE one: the marker comment exists only on the plan's own epic record, so a
satisfied reading is only reachable from the plan's own tenant.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands.plan import resume_directive
from livespec_orchestrator_beads_fabro.types import StoreConfig

_NOW = "2026-10-20T12:00:00Z"
_DESCRIPTION = "## Definition of Done\n\n- The plan reaches its archive.\n"
_BUDGET = {
    "deadline": "2099-10-10T12:00:00Z",
    "max_handoffs": 4,
    "epoch": "epoch-1",
    "handoff_count": 1,
}
# The plan's own repository, which is the invoking checkout's directory name: a
# tmp-path fixture is no git clone, so neither an origin remote nor a recorded
# primary path names it.
_OWN = "repo"
# The sibling that carried the plan's last satisfied obligation. Its clone is
# configured AND present, and it resolves a tenant connection of its own, so the
# satisfied reading that drives the advance is a real cross-tenant observation
# rather than a resolution failure wearing a satisfied label.
_CARRIER_REPO = "carrier-repo"
_CARRIER_ITEM = "bd-ib-carrier-child"
# A sibling whose clone exists but which configures no tenant of its own, so a
# read aimed at it is UNOBSERVABLE — the state the locked plan was measured in.
_STRANGER_REPO = "stranger-repo"
_PROOF_MARKER = "Plan Proof of Done"


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        repo_root=repo,
        fake=True,
    )


def _fake(*, repo: Path) -> FakeBeadsClient:
    client = make_beads_client(config=_config(repo=repo))
    assert isinstance(client, FakeBeadsClient)
    return client


def _connection(*, prefix: str) -> dict[str, object]:
    return {"livespec-orchestrator-beads-fabro": {"connection": {"prefix": prefix}}}


def _governed_project(*, tmp_path: Path) -> Path:
    """The plan's own checkout, beside a configured carrier and a configured stranger."""
    repo = tmp_path / _OWN
    repo.mkdir()
    configured: dict[str, object] = dict(_connection(prefix="bd-ib"))
    configured["cross_repo_targets"] = {
        name: {"github_url": f"https://github.com/thewoolleyman/{name}"}
        for name in (_CARRIER_REPO, _STRANGER_REPO)
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(configured), encoding="utf-8")
    carrier = tmp_path / _CARRIER_REPO
    carrier.mkdir()
    _ = (carrier / ".livespec.jsonc").write_text(
        json.dumps(_connection(prefix="bd-ib")), encoding="utf-8"
    )
    (tmp_path / _STRANGER_REPO).mkdir()
    return repo


def _seed_epic(
    *,
    repo: Path,
    epic_id: str,
    kind: str,
    ref: str,
    required_result: object,
) -> None:
    _ = _fake(repo=repo).create_issue(
        draft=IssueDraft(
            issue_id=epic_id,
            issue_type="epic",
            title=epic_id,
            description=_DESCRIPTION,
            assignee=None,
            created_at=_NOW,
            metadata={
                "next_action": {
                    "kind": kind,
                    "ref": ref,
                    "text": "Take the recorded next step.",
                    "required_result": required_result,
                    "budget": _BUDGET,
                },
                "last_session": f"plan-session at {_NOW}",
            },
        )
    )


def _pointer(*, repo: Path, epic_id: str) -> dict[str, object]:
    return dict(_fake(repo=repo).show_issue(issue_id=epic_id)["metadata"]["next_action"])


def test_a_derived_plan_step_names_the_plans_own_repository_not_the_carriers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The advance stamps the epic's own repository, whatever carried the last leg.

    The satisfied obligation names a sibling tenant, and the plan has no ready
    child left, so the advance derives the plan's proof leg. That leg's required
    result is a comment on the plan epic, which lives in the plan's own tenant —
    so the pointer must name the plan's own repository rather than the one the
    satisfied carrier happened to live in.
    """
    repo = _governed_project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _ = _fake(repo=repo).create_issue(
        draft=IssueDraft(
            issue_id=_CARRIER_ITEM,
            issue_type="task",
            title="a carrier child in a sibling tenant",
            description="The plan's last satisfied obligation.",
            assignee=None,
            created_at=_NOW,
        )
    )
    _fake(repo=repo).close_issue(issue_id=_CARRIER_ITEM, reason="the carrier landed")
    _seed_epic(
        repo=repo,
        epic_id="bd-ib-plan",
        kind="impl",
        ref=_CARRIER_ITEM,
        required_result={
            "repo": _CARRIER_REPO,
            "item_status": {"item_id": _CARRIER_ITEM, "status": "closed"},
        },
    )

    directive = resume_directive(config=_config(repo=repo), epic_id="bd-ib-plan", unattended=True)

    assert directive.observation is not None
    assert directive.observation.status == "satisfied"
    assert directive.observation.repo == _CARRIER_REPO
    assert directive.next_action == "proof:capture:bd-ib-plan"
    assert _pointer(repo=repo, epic_id="bd-ib-plan")["required_result"] == {
        "repo": _OWN,
        "item_comment": {"item_id": "bd-ib-plan", "marker": _PROOF_MARKER},
    }


def test_an_obligation_naming_the_plan_epic_elsewhere_is_read_from_the_plans_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pointer already poisoned must still be observable, or the plan stays locked.

    Both epics carry a recorded proof obligation on THEMSELVES under a sibling
    whose clone resolves and whose tenant does not, which is the state the
    measured plan was found in: the read fails, `resume_directive` reports
    `plan-progress-tracking: unobservable`, and no sanctioned write can replace
    an unobservable obligation. A plan epic lives in the plan's own tenant
    whatever its pointer says, so the read resolves there.

    The POSITIVE control is what separates "observable" from "read from the right
    tenant": the marker comment exists only on the plan's own epic record, so the
    satisfied reading — and the review leg it advances to — is reachable from no
    other tenant.
    """
    repo = _governed_project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    for epic_id in ("bd-ib-pointed", "bd-ib-proved"):
        _seed_epic(
            repo=repo,
            epic_id=epic_id,
            kind="proof",
            ref=f"capture:{epic_id}",
            required_result={
                "repo": _STRANGER_REPO,
                "item_comment": {"item_id": epic_id, "marker": _PROOF_MARKER},
            },
        )
    _fake(repo=repo).seed_comment(
        issue_id="bd-ib-proved",
        text=f"{_PROOF_MARKER} — captured — run 31f05f67 — {_NOW}",
        author="plan-session",
        created_at=_NOW,
    )

    unmet = resume_directive(config=_config(repo=repo), epic_id="bd-ib-pointed", unattended=True)
    met = resume_directive(config=_config(repo=repo), epic_id="bd-ib-proved", unattended=True)

    assert unmet.observation is not None
    assert unmet.observation.status == "unsatisfied"
    assert unmet.observation.repo == _OWN
    assert unmet.next_action == "proof:capture:bd-ib-pointed"
    # The READ redirects; it does not repair. The recorded pointer still names
    # the stranger, and the advance below is what replaces it with the plan's own
    # repository — so neither half of this fix stands in for the other.
    assert _pointer(repo=repo, epic_id="bd-ib-pointed")["required_result"] == {
        "repo": _STRANGER_REPO,
        "item_comment": {"item_id": "bd-ib-pointed", "marker": _PROOF_MARKER},
    }

    assert met.observation is not None
    assert met.observation.status == "satisfied"
    assert met.next_action == "review:bd-ib-proved"
    assert _pointer(repo=repo, epic_id="bd-ib-proved")["required_result"] == {
        "repo": _OWN,
        "item_comment": {
            "item_id": "bd-ib-proved",
            "marker": "plan-completeness-review-evidence",
        },
    }
