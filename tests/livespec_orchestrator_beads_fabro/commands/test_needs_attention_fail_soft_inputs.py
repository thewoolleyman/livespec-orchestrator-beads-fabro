"""One bad input costs the attention surface one finding, never the whole report.

Two gathers, two measured inputs (bd-ib-xbll72 and bd-ib-m2fb2g), one Red module so the
Red-Green-Replay hook sees exactly one staged test file.

PART 1 — a malformed plan-timeline comment costs one plan's finding, never the whole surface.

Measured 2026-10-25 ~04:10Z on the livespec-console-beads-fabro tenant with the
installed orchestrator build 4398f02e2502: `needs_attention.py --project-root
<console>` died after 76 s with `ValueError: Malformed plan timeline comment
01a1243f-eadc-7811-809c-61774ff7c208: missing author line`. The comment is a
LEGACY single-line handoff on epic livespec-console-beads-fabro-pzbdbo, written
2026-10-10T05:18:51Z before the structured `plan-handoff-entry` / `author: ` /
`timestamp: ` header existed:

    plan-handoff-entry (shutdown, 2026-10-10T05:25Z, session restarted by
    mistake and retired per overseer notice): no repo change this session. …

`read_timeline` now SKIPS such a comment and reports it through `on_skip`
(`test_plan_timeline` pins that). The operator attention surface was the place
the old refusal did the most harm: it is a read-only composition over every
plan, and one legacy comment on one epic erased the report for every other
plan, item and hygiene fact of the repository, on four of four fleet
repositories at once. Scenario 125's rule
("the enrichment is omitted and the valve item is still surfaced") is the shape
this gather already owed: the unreadable timeline becomes THAT plan's finding.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _drift_run_held
from livespec_orchestrator_beads_fabro.commands._drift_run_held import held_findings
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    plans,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
from livespec_orchestrator_beads_fabro.commands.plan import append_handoff
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_LEGACY_COMMENT = (
    "plan-handoff-entry (shutdown, 2026-10-10T05:25Z, session restarted by mistake and retired "
    "per overseer notice): no repo change this session. Facts a herdr successor needs: (1) the "
    "dispatch was REFUSED at the Definition-of-Done wall; author the section, then re-dispatch."
)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _epic(*, id_: str) -> WorkItem:
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=id_,
            issue_type="epic",
            title=f"{id_} title",
            description="d",
            assignee=None,
            created_at="2026-08-11T00:00:00Z",
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )
    return WorkItem(
        id=id_,
        type="epic",
        status="active",
        title=f"{id_} title",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=f"plan:{id_}-slug",
    )


def _healthy_handoff(*, epic_id: str) -> None:
    _ = append_handoff(
        config=_config(),
        epic_id=epic_id,
        body="Continue with the scoped child bd-ib-plan.1.",
        author="factory-test",
        now="2026-08-11T01:02:03Z",
        next_action=NextAction(
            kind="impl",
            ref=f"{epic_id}.1",
            text="Continue with the scoped child.",
            required_result={
                "repo": Path.cwd().name,
                "item_status": {"item_id": epic_id, "status": "closed"},
            },
            budget={"deadline": "2099-08-11T00:00:00Z", "max_handoffs": 3},
        ),
    )


def test_a_legacy_single_line_handoff_comment_is_that_plans_finding_not_a_crash(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    legacy = _epic(id_="bd-ib-legacy")
    _fake().seed_comment(
        issue_id="bd-ib-legacy", text=_LEGACY_COMMENT, created_at="2026-10-10T05:18:51Z"
    )
    healthy = _epic(id_="bd-ib-healthy")
    _healthy_handoff(epic_id="bd-ib-healthy")

    # At Red this raises the timeline reader's ValueError out of the gather,
    # which is the defect: the whole surface died on one legacy comment.
    outputs = plans(project_root=tmp_path, config=_config(), items=[legacy, healthy])

    by_topic = {output.topic: output for output in outputs}
    assert set(by_topic) == {"bd-ib-legacy-slug", "bd-ib-healthy-slug"}
    broken = by_topic["bd-ib-legacy-slug"]
    assert broken.urgency == "high"
    assert "Malformed plan timeline comment" in broken.summary
    assert "missing author line" in broken.summary
    # The healthy plan is still judged on its own timeline, never on the legacy
    # comment that sits on its sibling.
    assert "Malformed plan timeline comment" not in by_topic["bd-ib-healthy-slug"].summary


def test_a_malformed_comment_names_the_comment_so_the_operator_can_find_it(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    legacy = _epic(id_="bd-ib-legacy")
    _fake().seed_comment(issue_id="bd-ib-legacy", text="plan-scope-event\n\nno author line")
    [output] = plans(project_root=tmp_path, config=_config(), items=[legacy])
    assert "bd-ib-legacy" in output.summary


def test_a_skipped_comment_beside_a_valid_handoff_is_still_a_visible_finding(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    mixed = _epic(id_="bd-ib-mixed")
    _healthy_handoff(epic_id="bd-ib-mixed")
    _fake().seed_comment(issue_id="bd-ib-mixed", text=_LEGACY_COMMENT)
    other = _epic(id_="bd-ib-other")
    _healthy_handoff(epic_id="bd-ib-other")

    outputs = plans(project_root=tmp_path, config=_config(), items=[mixed, other])

    by_topic = {output.topic: output for output in outputs}
    assert set(by_topic) == {"bd-ib-mixed-slug", "bd-ib-other-slug"}
    assert by_topic["bd-ib-mixed-slug"].urgency == "high"
    assert "bd-ib-mixed comment #" in by_topic["bd-ib-mixed-slug"].summary
    assert "Malformed plan timeline comment" not in by_topic["bd-ib-other-slug"].summary


# PART 2 — a missing held-drift anchor, or a failing `bd comments`, reads no holds.
#
# Measured 2026-10-25 on livespec-dev-tooling, whose `.livespec.jsonc` declares no
# `detection_coverage_anchor`: `held_findings(anchor=None)` ran `bd comments  --json` with an
# EMPTY id, bd exited 1, and the BeadsCommandError — not among the absorbed exceptions —
# took the whole needs-attention composition down after 579 s (bd-ib-m2fb2g).
# `record_held_finding` already refuses a None or blank anchor; the read owes the same.

_ANCHOR = "bd-ib-anchor"


def _drift_config() -> StoreConfig:
    return StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )


@pytest.mark.parametrize("anchor", [None, "", "   "])
def test_a_missing_or_blank_anchor_reads_no_holds_and_asks_the_ledger_nothing(
    anchor: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset_fake_singleton()
    ledger = Mock(return_value=())
    monkeypatch.setattr(_drift_run_held, "read_work_item_comments", ledger)
    assert held_findings(path=_drift_config(), anchor=anchor) == ()
    # At Red the read asked `bd comments` for the EMPTY id, which bd refuses.
    assert ledger.call_count == 0, ledger.call_args_list


def test_a_failing_comments_command_reads_no_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bd failure is the OTHER way the read goes wrong, and it stays inside this gather."""
    reset_fake_singleton()
    refusal = BeadsCommandError(
        command=f"bd comments {_ANCHOR} --json", exit_code=1, stderr="bd: refused"
    )
    monkeypatch.setattr(_drift_run_held, "read_work_item_comments", Mock(side_effect=refusal))
    assert held_findings(path=_drift_config(), anchor=_ANCHOR) == ()
