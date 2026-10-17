"""A provider ceiling survives the needs-human terminal as a provider ceiling.

A provider usage or spend limit reaches the Dispatcher under the SAME generic
stage label as every other ACP fault, and it is PERMANENT for the rest of the
billing or rolling-usage window: retrying spends an allowance that is already
gone, and only a human or the clock clears it. `_fabro_port_records` therefore
reclassifies it out of fabro's own `transient_infra` into `deterministic`,
reads the refusing VENDOR off the cause rather than assuming one, and hands
both up as typed fields.

THE TERMINAL DROPPED BOTH. It passed no `provider_usage_limit` and no
`provider_usage_limit_provider`, so a ceiling observed at a needs-human ending
reached the ledger as an unclassified park — and the dispatcher-owned hold that
stops the next dispatch burning the same exhausted credential was never
written, because the recorder keys on exactly that provider field.

WHY THE HOLD IS ASSERTED AND NOT JUST THE FIELDS. "Survives" is a claim about a
CONSUMER, and `record_provider_exhaustion_if_observed` is the consumer that
matters: it is what converts the observation into a refusal the next dispatch
honours. Asserting the two fields alone would pass for a build that carried
them to a surface nothing reads.

WHY TWO VENDORS. Detection is deliberately vendor-agnostic and the vendor is
READ OFF the cause, so a fixed label would record an Anthropic ceiling under
the Codex vendor — which then refuses the next dispatch citing an exhaustion
that never happened while holding no record for the vendor that actually
refused. Both measured forms are exercised, and each must produce its own
vendor.

AND IT IS NOT A TRANSPORT FAULT. The carrier worked; the model declined. The
transport-fault classification is asserted ABSENT so the two cannot collapse
into one label with one remedy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
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

_ITEM = "bd-ib-ceiling"
_RUN = "01M4PROVIDERCEILINGTERMINAL"
# Fabro's OWN classification, which the permanent-cause pass must overrule.
_RAW_SIGNATURE = "implement|transient_infra|acp turn failed"
_RECLASSIFIED_SIGNATURE = "implement|deterministic|acp turn failed"
_CODEX_CAUSE = (
    "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
    "for details or try again at 2026-10-09T18:00:00Z"
)
_ANTHROPIC_CAUSE = "You've hit your org's monthly spend limit. Visit claude.ai/settings/usage"
_STDERR = (
    f"{NEEDS_HUMAN_MARKER}_PRESERVED: refs/heads/needs-human/{_RUN}\n"
    f"{NEEDS_HUMAN_MARKER}: loop cannot auto-resolve this work-item; run terminated, "
    "work preserved by reference, decision routed to the ledger (blocked / needs-human)\n"
)
_NOW = "2026-10-09T12:00:00Z"


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _payload(*, cause: str) -> list[object]:
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
                                    "causes": ["ACP protocol error", cause],
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


def _outcome(*, tmp_path: Path, cause: str) -> DispatchOutcome:
    payload = _payload(cause=cause)
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
    # SUPERSEDED, and deliberately re-pointed rather than dropped. This guard
    # read `blocked` until `bd-ib-6itdjz` landed the provider-limit release of
    # `SPECIFICATION/contracts.md`'s "Provider-limit release and re-dispatch":
    # a ceiling observed at a terminal now releases the item to `ready` instead
    # of resting it at `blocked / needs-human`, which the clause forbids
    # surfacing as a needs-human decision at all.
    #
    # Everything this module asserts BELOW the guard is unchanged and is now
    # the live proof that the release did not cost the legacy observation: the
    # two typed provider fields still ride the outcome, the taxonomy is still
    # overruled to `deterministic`, and `record_provider_exhaustion_if_observed`
    # still writes its record -- which it keys on
    # `provider_usage_limit_provider` alone, so a release that dropped that
    # field would leave the next dispatch burning the same exhausted
    # credential.
    assert outcome.status == "provider-limit-release"
    return outcome


@pytest.mark.parametrize(
    ("cause", "provider"),
    [(_CODEX_CAUSE, "codex"), (_ANTHROPIC_CAUSE, "anthropic")],
)
def test_the_ceiling_and_its_vendor_survive_the_terminal_and_reach_the_hold(
    tmp_path: Path,
    cause: str,
    provider: str,
) -> None:
    """Both typed fields, the overruled taxonomy, and the consumer that uses them."""
    outcome = _outcome(tmp_path=tmp_path, cause=cause)
    journal = _RecordingJournal()

    record_provider_exhaustion_if_observed(
        outcome=outcome, journal=journal, journal_path=None, now_iso=_NOW
    )

    assert outcome.provider_usage_limit is True
    assert outcome.provider_usage_limit_provider == provider
    # Fabro called this transient; a ceiling a retry cannot clear is not.
    assert outcome.fabro_failure_category == "deterministic"
    assert outcome.fabro_failure_signature == _RECLASSIFIED_SIGNATURE
    assert outcome.fabro_failure_cause == cause
    # The consumer that turns the observation into the next dispatch's refusal.
    # `credential_identity` is an explicit null here, because no journal was
    # handed in and so no admission assessment could have named an account --
    # the key is still written, so a reader can tell that from a record minted
    # before accounts were named at all.
    assert journal.records == [
        {
            "at": _NOW,
            "stage": "provider-exhaustion-observed",
            "work_item_id": _ITEM,
            "provider": provider,
            "credential_identity": None,
            "governing_condition": "provider_usage_limit",
            "record_expires_at": "2026-10-09T12:15:00Z",
        }
    ]


def test_a_ceiling_is_rendered_as_a_ceiling_and_never_as_a_transport_fault(
    tmp_path: Path,
) -> None:
    """The carrier worked; the model declined. One label, one remedy, each."""
    detail = _outcome(tmp_path=tmp_path, cause=_CODEX_CAUSE).detail

    assert "failed at stage implement" in detail
    assert _CODEX_CAUSE in detail
    assert "transport fault" not in detail
