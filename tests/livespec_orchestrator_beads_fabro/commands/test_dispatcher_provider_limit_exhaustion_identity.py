"""A usage-limit RELEASE still mints the account-scoped provider-exhaustion record.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Provider-limit release and re-dispatch" (`bd-ib-6itdjz`,
Scenario 127) releases a provider-limited item to `ready` instead of resting it
at `blocked / needs-human`. That release gave the outcome its OWN status, and
THAT is what this module exists to guard: the legacy provider observation is
minted by `record_provider_exhaustion_if_observed`, which runs in the post-run
sequence beside the terminal routing rather than inside it, so a release that
had stopped carrying the two typed provider fields -- or a sequence step gated
on the `blocked`/`failed` statuses the release no longer uses -- would silently
stop writing the record that stops the NEXT dispatch burning the same spent
allowance.

WHY THIS IS NOT ALREADY COVERED NEXT DOOR.
`test_dispatcher_needs_human_provider_limit.py` asserts the record survives the
release, and it is the right place for that claim. But it hands
`journal_path=None`, so the `credential_identity` it asserts is an explicit
NULL -- which is the honest answer for a caller holding no journal and is
exactly the value a build that had lost the account read would also produce.
The clause requires the record to carry "the opaque non-secret credential
identity that the dispatch's admission session-headroom assessment journaled",
and a null assertion cannot distinguish "this dispatch projected no account"
from "the identity read is broken". So the identity half needs a journal that
actually names one.

WHY THE ACCOUNT RATHER THAN THE VENDOR IS THE LOAD-BEARING FIELD. The account
behind one vendor is swapped by a selection process outside the Dispatcher, so
a record labelled only `anthropic` cannot tell a spent account from a fresh
one; `_dispatcher_exhaustion_credential_identity`'s own docstring records the
2026-10-16 measurement where four in-flight runs on the rotated-off account
minted records that refused every dispatch on the NEW account. A release that
dropped the identity re-opens exactly that confusion, and it re-opens it
silently, because the record still reads as a perfectly well-formed hold.

TWO IDENTITIES ARE PARAMETRIZED, which is the control. One identity asserted
once would pass against an implementation that echoed a literal, or that read
the identity from anywhere other than this dispatch's own journaled
assessment; two distinct journals whose records must follow them cannot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    record_provider_exhaustion_if_observed,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)

_ITEM = "bd-ib-plexhaust"
_RUN = "01M52R2WND7Y"
_NOW = "2026-10-16T19:20:00Z"
_RAW_SIGNATURE = "implement|transient_infra|acp turn failed"
# The measured Anthropic session-limit sentence `_ANTHROPIC_SESSION_LIMIT`
# matches, from the 2026-10-16 outage this item's own rider records: four runs
# ended this way in one day, each with real preserved progress.
_SESSION_LIMIT_CAUSE = "You have hit your session limit, resets 7:20pm (UTC)"
_STDERR = (
    f"{NEEDS_HUMAN_MARKER}_PRESERVED: refs/heads/needs-human/{_RUN}\n"
    f"{NEEDS_HUMAN_MARKER}: loop cannot auto-resolve this work-item\n"
)


def _payload() -> list[object]:
    """`fabro inspect --json` for a run the engine routed to the terminal."""
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed"},
            "checkpoints": [
                {
                    "checkpoint": {
                        "next_node_id": "needs_human",
                        "loop_failure_signatures": {_RAW_SIGNATURE: 1},
                        "node_outcomes": {
                            "implement": {
                                "failure": {
                                    "category": "transient_infra",
                                    "signature": _RAW_SIGNATURE,
                                    "causes": ["ACP protocol error", _SESSION_LIMIT_CAUSE],
                                }
                            }
                        },
                    }
                }
            ],
        }
    ]


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server="https://hp.example:32276",
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _release_outcome(*, tmp_path: Path) -> DispatchOutcome:
    """The real terminal mapping, so the fields under test are the ones it sets."""
    payload = _payload()
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=payload,
            status_kind=fabro_status_kind_from_payload(payload=payload),
            failure=fabro_failure_detail_from_payload(payload=payload),
        ),
        exit_code=1,
        stderr=_STDERR,
    )
    assert outcome is not None
    # THE SUBJECT IS A RELEASE. Without this the module would assert the
    # identity on whatever route the terminal happened to take, and would keep
    # passing if the release regressed to the `blocked` park the clause forbids.
    assert outcome.status == "provider-limit-release"
    # And it is a USAGE limit, which is the arm that owes a legacy observation.
    assert outcome.provider_usage_limit is True
    return outcome


def _journal_naming(*, tmp_path: Path, identity: str) -> JournalFile:
    """A dispatch journal whose admission assessment named `identity`."""
    path = tmp_path / "journal.jsonl"
    _ = path.write_text(
        json.dumps(
            {
                "at": "2026-10-16T19:00:00Z",
                "stage": SESSION_HEADROOM_STAGE,
                "work_item_id": _ITEM,
                "assessments": [{"credential_identity": identity}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return JournalFile(path=path)


def _exhaustion_records(*, journal: JournalFile) -> list[dict[str, object]]:
    """Only the minted observations, read back off the file the append wrote.

    Read back from the FILE rather than from a recording double, because the
    identity is read from that same file and a double would let the test pass
    against a journal the production append never actually landed in.
    """
    lines: list[str] = journal.path.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, object]] = [json.loads(line) for line in lines]
    return [record for record in records if record.get("stage") == "provider-exhaustion-observed"]


@pytest.mark.parametrize("identity", ["anthropic-1", "anthropic-3"])
def test_a_usage_limit_release_records_the_journaled_credential_identity(
    tmp_path: Path,
    identity: str,
) -> None:
    """The record names the ACCOUNT this dispatch's own assessment journaled."""
    outcome = _release_outcome(tmp_path=tmp_path)
    journal = _journal_naming(tmp_path=tmp_path, identity=identity)

    record_provider_exhaustion_if_observed(
        outcome=outcome,
        # The journal being APPENDED to is the journal being READ, exactly as
        # `post_run_dispositions` threads it: a path re-derived from a
        # repository root cannot be proven to name the file the assessment was
        # written into, which is the wrong-population read that would label
        # every record with no account at all.
        journal=journal,
        journal_path=journal.path,
        now_iso=_NOW,
    )

    records = _exhaustion_records(journal=journal)
    # EXACTLY ONE, so a release cannot mint a second hold for one observation.
    assert len(records) == 1
    assert records[0]["credential_identity"] == identity
    assert records[0]["provider"] == "anthropic"
    assert records[0]["governing_condition"] == "provider_usage_limit"
    assert records[0]["work_item_id"] == _ITEM
