"""A provider ceiling is attributed to the candidate that actually ran.

`SPECIFICATION/contracts.md` section "Provider-limit permanence and root-cause
surfacing": "The provider is attributed from the recorded executed candidate
identity, never inferred from a shared message literal." Scenario 65's "A
shared provider sentence is attributed to the candidate that ran" is the case
that makes the rule necessary.

WHY A SENTENCE CANNOT NAME THE VENDOR. Claude and Codex both say "You've hit
your usage limit", so the hint list that recognises the ceiling cannot also
decide whose allowance is gone. Measured 2026-10-12 (investigation D2,
`plan/factory-configurable-model-fallback-priority/research/
dispatcher-fallback-downsides-2026-10-12.md`), the hint maps that sentence to
`codex`, which is wrong in BOTH directions at once when the failing attempt
ran on Claude: the dispatcher-owned record then refuses dispatches on an
allowance nothing spent while leaving the spent one unheld.

THE TWO CONTROLS ARE THE LOAD-BEARING ONES. An identity-less legacy adapter
keeps the v107 cause-text attribution, because the contract keeps that adapter
on "the conservative legacy posture" and there is no entitlement to scope a
hold by; and a recorded identity must not be able to MANUFACTURE a ceiling,
because the labels are stamped on every dispatch while a provider ceiling is
rare, so an attribution that applied itself to any failure would label every
ordinary fault with a vendor.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroFailureDetail,
    fabro_failure_detail_from_payload,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._fabro_executed_candidate"
_SOURCE = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_fabro_executed_candidate.py"
)

_ACP_WRAPPER = "ACP protocol error"
# The sentence BOTH vendors emit, with no reset instant and no vendor marker:
# everything the cause text can offer about whose allowance it was, which is
# nothing.
_SHARED_SENTENCE = "the agent answered `session/prompt` with an error: You've hit your usage limit"
# A fault that is no ceiling at all, for the manufacture control.
_ORDINARY_FAULT = "connection reset by peer"

# The labels ONE dispatch stamped: the implementer ran on Claude, the
# disposition node on Codex. Both pairs are present so a reader keyed on the
# wrong node still finds a well-formed answer rather than nothing, which is
# what makes the per-node scoping assertion below able to fail.
_RUN_LABELS = {
    "livespec.repository": "livespec-orchestrator-beads-fabro",
    "livespec.acp.implement.availability": "anthropic",
    "livespec.acp.implement.candidate": "builtin-anthropic-9f2c1d0b4e5a6f78",
    "livespec.acp.disposition.availability": "codex",
    "livespec.acp.disposition.candidate": "builtin-codex-1a2b3c4d5e6f7081",
}


def _module() -> Any:
    """The module under test, proving its file exists before importing it."""
    assert _SOURCE.is_file(), f"{_SOURCE} has not been written yet"
    return importlib.import_module(_MODULE)


def _failure(*, cause: str) -> FabroFailureDetail:
    """One pinned-engine failure detail, classified as it arrives today."""
    detail = fabro_failure_detail_from_payload(
        payload=[
            {
                "status": {"kind": "failed"},
                "failure": {
                    "causes": [_ACP_WRAPPER, cause],
                    "category": "transient_infra",
                    "signature": "implement|transient_infra|acp turn failed",
                },
            }
        ]
    )
    assert detail is not None
    return detail


def test_the_provider_and_entitlement_come_from_the_recorded_executed_candidate() -> None:
    """The failing attempt's own identity supplies both, not the sentence."""
    module = _module()
    arriving = _failure(cause=_SHARED_SENTENCE)
    assert arriving.provider_usage_limit is True
    assert arriving.provider_usage_limit_provider == "codex"

    executed = module.executed_candidate_identity(labels=_RUN_LABELS, node="implement")
    attributed = module.attributed_provider_limit_failure(failure=arriving, executed=executed)

    assert executed.node == "implement"
    assert executed.availability_key == "anthropic"
    assert executed.candidate_key == "builtin-anthropic-9f2c1d0b4e5a6f78"
    assert attributed.provider_usage_limit is True
    assert attributed.provider_usage_limit_provider == "anthropic"
    assert attributed.provider_usage_limit_entitlement == "builtin-anthropic-9f2c1d0b4e5a6f78"


def test_the_identity_is_read_for_the_failing_node_and_never_for_a_sibling() -> None:
    """One run stamps every node, so the NODE is what selects the entitlement."""
    module = _module()
    arriving = _failure(cause=_SHARED_SENTENCE)

    disposition = module.executed_candidate_identity(labels=_RUN_LABELS, node="disposition")
    attributed = module.attributed_provider_limit_failure(failure=arriving, executed=disposition)

    assert disposition.availability_key == "codex"
    assert attributed.provider_usage_limit_provider == "codex"
    assert attributed.provider_usage_limit_entitlement == "builtin-codex-1a2b3c4d5e6f7081"


def test_an_unlabelled_failing_node_keeps_the_v107_cause_text_attribution() -> None:
    """CONTROL: an identity-less legacy adapter stays on the v107 posture.

    `dispatch_run_label_pairs` emits a pair only for a node that resolved an
    identity, so an identity-less legacy adapter leaves its node unlabelled —
    and the conservative legacy attribution is the whole reason that adapter
    may carry no identity at all.
    """
    module = _module()
    arriving = _failure(cause=_SHARED_SENTENCE)

    assert module.executed_candidate_identity(labels=_RUN_LABELS, node="janitor") is None
    assert module.executed_candidate_identity(labels={}, node="implement") is None
    assert module.executed_candidate_identity(labels=_RUN_LABELS, node=None) is None

    unattributed = module.attributed_provider_limit_failure(failure=arriving, executed=None)

    assert unattributed.provider_usage_limit is True
    assert unattributed.provider_usage_limit_provider == "codex"
    assert unattributed.provider_usage_limit_entitlement is None


def test_a_recorded_identity_cannot_manufacture_a_ceiling_nothing_reported() -> None:
    """CONTROL: attribution reports a vendor only where one refused.

    Every dispatch stamps these labels while a provider ceiling is rare, so an
    attribution that fired on any failure would name a vendor for an ordinary
    transport fault — and `provider_usage_limit_provider` is non-None exactly
    when the typed flag is set, an invariant `FabroFailureDetail` states.
    """
    module = _module()
    ordinary = _failure(cause=_ORDINARY_FAULT)
    assert ordinary.provider_usage_limit is False

    executed = module.executed_candidate_identity(labels=_RUN_LABELS, node="implement")
    attributed = module.attributed_provider_limit_failure(failure=ordinary, executed=executed)

    assert attributed.provider_usage_limit is False
    assert attributed.provider_usage_limit_provider is None
    assert attributed.provider_usage_limit_entitlement is None
    assert module.attributed_provider_limit_failure(failure=None, executed=executed) is None
