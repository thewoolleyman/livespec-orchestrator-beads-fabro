"""Journal-backed wait attention lanes for needs-attention."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_acp_preflight,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    dispatch_provider_exhaustion,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    dispatcher_loop_command,
    host_only_command,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "acceptance_wait_summary",
    "acp_chain_wait_active",
    "host_only_items",
    "provider_exhaustion_items",
    "provider_exhaustion_wait_active",
]

_HOST_ONLY_REFUSAL_STAGE = "host-only-refused"
_RECORDED_REFUSAL_REASON = "recorded-refusal"
_DISPATCHER_JOURNAL_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"
_NEEDS_ATTENTION_VERDICT = "NEEDS_ATTENTION"


def acceptance_wait_summary(
    *,
    project_root: Path,
    item: WorkItem,
    default_summary: str,
) -> str:
    park = _latest_record(project_root=project_root, item_id=item.id, stage="acceptance-parked")
    if _str_field(record=park, key="acceptance_verdict") != _NEEDS_ATTENTION_VERDICT:
        return default_summary
    absent = _absent_evidence_legs(project_root=project_root, item_id=item.id, park=park)
    return (
        f"{default_summary}; NEEDS_ATTENTION acceptance park "
        f"with absent evidence: {', '.join(absent)}. "
        f"Available actions: accept:{item.id}, reject:{item.id}:rework, "
        f"reject:{item.id}:regroom."
    )


def host_only_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
) -> list[AttentionItem]:
    reasons = _host_only_reasons(project_root=project_root, items=items)
    return [
        _host_only_item(project_root=project_root, repo=repo, work_item=item_id, reason=reason)
        for item_id, reason in reasons.items()
    ]


def provider_exhaustion_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
) -> list[AttentionItem]:
    record = dispatch_provider_exhaustion(
        journal_path=project_root / _DISPATCHER_JOURNAL_PATH,
        now_iso=utc_now_iso(),
    )
    if record is None:
        return []
    return [
        _provider_exhaustion_item(
            project_root=project_root,
            repo=repo,
            item=item,
            provider=record.provider,
        )
        for item in items
        if item.status == "ready" and item.factory_safety is None
    ]


def provider_exhaustion_wait_active(*, project_root: Path) -> bool:
    return (
        dispatch_provider_exhaustion(
            journal_path=project_root / _DISPATCHER_JOURNAL_PATH,
            now_iso=utc_now_iso(),
        )
        is not None
    )


def acp_chain_wait_active(*, project_root: Path) -> bool:
    """Whether an exhausted success-critical ACP candidate chain holds dispatch.

    This is the WAIT-ATTENTION half of the one preflight verdict admission
    consumes, and it consumes it the way `SPECIFICATION/contracts.md` section
    "Factory-configurable ACP fallback priority" requires: "Idle-factory and
    wait attention consume this identical verdict."

    No probe is supplied, so the read performs no credential assessment and no
    other external call -- it composes this repository's own committed
    configuration, workflow graph and journal, and nothing else. That is what
    lets the idle-factory row it gates stay byte-identical across two passes
    over an unchanged store.
    """
    return not resolve_acp_preflight(
        repo=project_root,
        journal_path=project_root / _DISPATCHER_JOURNAL_PATH,
        now_iso=utc_now_iso(),
    ).viable


def _provider_exhaustion_item(
    *,
    project_root: Path,
    repo: str,
    item: WorkItem,
    provider: str,
) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        # `provider-exhaustion` is not a ratified stable-ID prefix, so this id
        # failed the runtime validator outright. It rides the orchestrator-owned
        # `hygiene:<type>:<resource>` form instead; the resource keeps both
        # identifying components verbatim, which the grammar admits because it
        # splits the id at most twice.
        id=f"hygiene:provider-exhaustion:{provider}:{item.id}",
        kind="internal",
        urgency="high",
        summary=_provider_exhaustion_summary(project_root=project_root, work_item=item.id),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=Handoff(
            kind="shell",
            command=(
                f"{dispatcher_loop_command(project_root=project_root)} "
                "# Dispatcher admission pass"
            ),
        ),
    )


def _provider_exhaustion_summary(*, project_root: Path, work_item: str) -> str:
    record = cast(
        "Any",
        dispatch_provider_exhaustion(
            journal_path=project_root / _DISPATCHER_JOURNAL_PATH,
            now_iso=utc_now_iso(),
        ),
    )
    return (
        f"Work-item {work_item} awaits provider-exhaustion expiry: "
        f"provider={record.provider} "
        f"governing_condition={record.governing_condition} "
        f"record_expires_at={record.record_expires_at}."
    )


def _host_only_reasons(*, project_root: Path, items: list[WorkItem]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for item in items:
        if item.status != "done" and item.factory_safety is not None:
            reasons[item.id] = item.factory_safety
    for item_id in _recorded_host_only_refusals(project_root=project_root):
        _ = reasons.setdefault(item_id, _RECORDED_REFUSAL_REASON)
    return reasons


def _recorded_host_only_refusals(*, project_root: Path) -> tuple[str, ...]:
    item_ids: list[str] = []
    for record in _journal_records(project_root=project_root):
        item_id = _host_only_refusal_item_id(record=record)
        if item_id is not None:
            item_ids.append(item_id)
    return tuple(dict.fromkeys(item_ids))


def _host_only_refusal_item_id(*, record: dict[str, Any]) -> str | None:
    if record.get("stage") != "outcome":
        return None
    outcome = record.get("outcome")
    if not isinstance(outcome, dict):
        return None
    outcome_record = cast("dict[str, Any]", outcome)
    if outcome_record.get("stage") != _HOST_ONLY_REFUSAL_STAGE:
        return None
    item_id = outcome_record.get("work_item_id")
    return item_id if isinstance(item_id, str) else None


def _host_only_item(
    *,
    project_root: Path,
    repo: str,
    work_item: str,
    reason: str,
) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"host-only:{reason}:{work_item}",
        kind="host-only",
        urgency="high",
        summary=f"Host-route work-item {work_item}: factory_safety {reason}.",
        source_ref=SourceRef(repo=repo, work_item=work_item),
        handoff=Handoff(
            kind="shell",
            command=host_only_command(project_root=project_root, work_item=work_item),
        ),
    )


def _latest_record(*, project_root: Path, item_id: str, stage: str) -> dict[str, Any] | None:
    for record in reversed(_journal_records(project_root=project_root)):
        if record.get("stage") == stage and record.get("work_item_id") == item_id:
            return record
    return None


def _journal_records(*, project_root: Path) -> tuple[dict[str, Any], ...]:
    journal = project_root / _DISPATCHER_JOURNAL_PATH
    if not journal.is_file():
        return ()
    loaded = attempt(action=lambda: journal.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(loaded, AttemptFailure):
        return ()
    records: list[dict[str, Any]] = []
    for line in loaded.splitlines():
        record = _json_object(line=line)
        if record is not None:
            records.append(record)
    return tuple(records)


def _json_object(*, line: str) -> dict[str, Any] | None:
    parsed = attempt(action=lambda: json.loads(line), exceptions=(json.JSONDecodeError,))
    loaded = cast("object", parsed)
    if isinstance(loaded, AttemptFailure) or not isinstance(loaded, dict):
        return None
    return cast("dict[str, Any]", loaded)


def _absent_evidence_legs(
    *,
    project_root: Path,
    item_id: str,
    park: dict[str, Any] | None,
) -> tuple[str, ...]:
    """Name the legs the acceptance pass could not observe, the empty diff included.

    The park record's OWN `absent_evidence` is authoritative whenever it carries
    one. The pass names its legs knowing the item's change classification, so a
    zero-change merged run arrives here ALREADY named as the empty-diff
    merged-diff leg — which is exactly what this composition's summary must name,
    per the parked-acceptance arity and distinguishability rule of
    `SPECIFICATION/contracts.md` — while a declared change-optional item, whose empty
    merged diff IS observed evidence, arrives with no merged-diff leg named at
    all. Re-deriving either answer here would put a second copy of the
    classification rule in a module that cannot even see the item's labels, and
    two copies of one rule are how the two surfaces come to disagree about the
    same item.

    The per-leg `observed` derivation is the FALLBACK, and only that: this
    composition shipped two days before the park record carried a named list, so
    a park record from that window has the per-leg observations and nothing else.
    Naming those beats naming nothing, but it cannot distinguish an empty merged
    diff from an unreadable one, because the record it reads does not say.
    """
    recorded = _recorded_absent_evidence(record=park)
    if recorded is not None:
        return recorded
    return _observed_leg_names(
        record=_latest_record(
            project_root=project_root,
            item_id=item_id,
            stage="acceptance-ai-pass",
        )
    )


def _recorded_absent_evidence(*, record: dict[str, Any] | None) -> tuple[str, ...] | None:
    """The legs the park record names itself, or `None` when it names none.

    An `absent_evidence` that is missing, is not a list, or is empty names
    nothing: a NEEDS_ATTENTION park always has at least one absent leg, so an
    empty list is a malformed record rather than a park with nothing absent.
    """
    listed = cast("dict[str, Any]", record).get("absent_evidence")
    if not isinstance(listed, list) or not listed:
        return None
    legs = cast("list[Any]", listed)
    return tuple(str(leg) for leg in legs)


def _observed_leg_names(*, record: dict[str, Any] | None) -> tuple[str, ...]:
    acceptance_record = cast("dict[str, Any]", record)
    absent = [
        name
        for name in ("diff", "criteria", "telemetry")
        if not _observed(record=acceptance_record, key=name)
    ]
    return tuple(absent)


def _observed(*, record: dict[str, Any], key: str) -> bool:
    leg = cast("dict[str, Any]", record.get(key))
    return leg.get("observed") is True


def _str_field(*, record: dict[str, Any] | None, key: str) -> str | None:
    if record is None:
        return None
    value = record.get(key)
    return value if isinstance(value, str) else None
