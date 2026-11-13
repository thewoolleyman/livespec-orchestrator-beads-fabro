"""The generic incident transition cannot close a recorded drill."""

from __future__ import annotations

import json
from dataclasses import replace

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_authority
from livespec_orchestrator_beads_fabro.effects._incident_authority_transition import (
    commit_transition,
)


def test_generic_transition_refuses_a_drill_closed_successor() -> None:
    client = FakeBeadsClient()
    item_id = "bd-ib-drill"
    client.create_issue(
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="bug",
            title="drill",
            description="recorded drill",
            assignee=None,
            created_at="2026-11-13T00:00:00Z",
        )
    )
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority root")
    token = client.create_no_history_issue(title=TOKEN_TITLE, description="authority token")
    attempt = {
        "repository": "owner/repository",
        "item_id": item_id,
        "attempt_id": "drill-1",
        "phase": "reverting",
        "operation_id": "drill-1#reverting",
        "generation": 1,
        "owner": "operator:alice",
        "base": "a" * 40,
        "head": "b" * 40,
        "pr_number": 7,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": ["app.py"],
        "deferred_work": ["normal-factory-proof"],
        "repayment_required": True,
    }
    client.add_comment(
        issue_id=item_id,
        body=GENESIS_MARKER
        + '{"item_id":"bd-ib-drill","repository":"owner/repository","root_token_id":"'
        + root
        + '","schema":1}',
    )
    client.close_issue_without_verdict(
        issue_id=root,
        reason=TRANSITION_MARKER
        + '{"attempt":'
        + json.dumps(attempt, sort_keys=True, separators=(",", ":"))
        + ',"item_id":"bd-ib-drill","next_token_id":"'
        + token
        + '","prior_token_id":"'
        + root
        + '","repository":"owner/repository","schema":1}',
    )
    reading = read_authority(
        client=client,
        repository="owner/repository",
        item_id=item_id,
        query={
            key: attempt[key]
            for key in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
        historical=False,
    )
    assert isinstance(reading, IncidentReading)
    successor = replace(
        reading.attempt,
        phase="drill-closed",
        operation_id="drill-1#drill-close",
        generation=2,
        repayment_required=False,
    )

    refused = commit_transition(client=client, observed=reading, successor=successor)

    assert isinstance(refused, AuthorityRefusal)
    assert (refused.code, refused.detail) == ("incident-drill-close-requires-action", item_id)
