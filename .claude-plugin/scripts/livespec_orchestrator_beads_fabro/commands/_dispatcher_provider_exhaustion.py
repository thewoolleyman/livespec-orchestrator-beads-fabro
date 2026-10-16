"""Provider-exhaustion admission records for the Dispatcher."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import (
    RenderedCandidate,
    legacy_record_covers_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_exhaustion_credential_identity import (
    journaled_admission_credential_identity,
    record_identity_covers_dispatch,
)
from livespec_orchestrator_beads_fabro.effects import parse_iso_datetime

__all__: list[str] = [
    "ProviderExhaustionRecord",
    "active_provider_exhaustion",
    "covering_provider_exhaustion",
    "dispatch_provider_exhaustion",
    "live_provider_exhaustions",
    "provider_exhaustion_clearance_record",
    "provider_exhaustion_refusal",
    "record_provider_exhaustion_if_observed",
]

_GOVERNING_CONDITION = "provider_usage_limit"

# NO VENDOR LIST LIVES HERE ANY MORE, and its absence is the fix rather than
# an omission. A hard-coded `("anthropic", "codex")` tuple used to stand in for
# "the vendors a dispatch spends", and it was wrong in BOTH directions at once:
# a record for either vendor refused EVERY dispatch — including one routed
# wholly to the other — while a record naming any third provider was
# unreadable, which surfaced as a clean, plausible "no record held".
#
# Both halves are now DERIVED. `live_provider_exhaustions` enumerates whatever
# providers the journal's own records name, so the readable set is a fact about
# the records; and `covering_provider_exhaustion` asks each live record whether
# it covers a candidate THIS DISPATCH'S RESOLVED NODE ADAPTERS render, so the
# refusable set is a fact about the adapters. Keying the record on the observed
# vendor (`_fabro_port_records`) and the gate on the rendered candidates is
# what keeps one vendor's ceiling from silently standing in for another's.

_RECORD_STAGE = "provider-exhaustion-observed"
_REFUSAL_STAGE = "provider-exhaustion-refusal"
# The operator's early-clearance line. It RETIRES the newest observation for
# its provider instead of rewriting or deleting it: the journal is append-only
# by construction, so what was observed and who overrode it both survive.
_CLEARED_STAGE = "provider-exhaustion-cleared"
_HOLD_INTERVAL = timedelta(minutes=15)


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


class _Outcome(Protocol):
    @property
    def work_item_id(self) -> str:
        """Ledger id for the dispatch outcome."""
        ...

    @property
    def provider_usage_limit_provider(self) -> str | None:
        """The vendor whose ceiling the completed Fabro run observed, if any."""
        ...


@dataclass(frozen=True, kw_only=True)
class ProviderExhaustionRecord:
    provider: str
    governing_condition: str
    record_expires_at: str
    work_item_id: str
    credential_identity: str | None = None


def record_provider_exhaustion_if_observed(
    *,
    outcome: _Outcome,
    journal: _Journal,
    journal_path: Path | None,
    now_iso: str,
) -> None:
    """Persist a short dispatcher-owned hold from a typed provider limit outcome.

    The record is labelled with the vendor the RUN observed, never with a fixed
    one. The outcome's provider field is the trigger as well as the label, so
    there is no second condition that could disagree with it and no path on
    which a record is written under a vendor nothing was measured against.

    IT IS ALSO LABELLED WITH THE ACCOUNT, read from what this dispatch's own
    admission session-headroom assessment journaled. `journal_path` is the
    journal this disposition is APPENDING to rather than one re-derived from a
    repository root, because `dispatcher.py` accepts a `--journal` override and
    a second derivation cannot be proven to name the file the assessment was
    written into -- the wrong-population reading that would silently label
    every record with no account at all. It is a required parameter rather
    than a defaulted one for the same reason: `None` is the honest answer for
    a caller holding no journal, while a default would let a caller that
    simply forgot to thread it through mint vendor-only records forever.

    THE KEY IS WRITTEN EVEN WHEN THERE IS NO IDENTITY, null included, exactly
    as the session-headroom reading writes its own nulls: an omitted key is
    what a record from a build predating this clause looks like, so a reader
    could not tell "this dispatch projected no account" from "this record was
    minted before accounts were named".
    """
    provider = outcome.provider_usage_limit_provider
    if provider is None:
        return
    now = _parse_journal_iso(text=now_iso)
    expires_at = (now + _HOLD_INTERVAL).strftime("%Y-%m-%dT%H:%M:%SZ")
    journal.append(
        record={
            "at": now_iso,
            "stage": _RECORD_STAGE,
            "work_item_id": outcome.work_item_id,
            "provider": provider,
            "credential_identity": journaled_admission_credential_identity(
                journal_path=journal_path, work_item_id=outcome.work_item_id
            ),
            "governing_condition": _GOVERNING_CONDITION,
            "record_expires_at": expires_at,
        }
    )


def provider_exhaustion_clearance_record(*, provider: str, reason: str) -> dict[str, object]:
    """Build the appended line that retires one provider's newest observation.

    The record carries only what the CLEARANCE itself asserts — the vendor and
    the operator's stated reason. `at`, `invoker` and `invoker_source` are
    stamped by the append layer, which is what makes "who cleared it, and
    when" the same unforgeable claim on this record as on the observation it
    retires.
    """
    return {
        "stage": _CLEARED_STAGE,
        "provider": provider,
        "governing_condition": _GOVERNING_CONDITION,
        "reason": reason,
    }


def live_provider_exhaustions(
    *,
    journal_path: Path | None,
    now_iso: str,
) -> tuple[ProviderExhaustionRecord, ...]:
    """Every (provider, account)'s newest unexpired record, newest first.

    WHICH PROVIDERS EXIST IS A FACT ABOUT THE JOURNAL, not about any list this
    build carries. A record naming a vendor nothing here anticipated is read
    exactly as `anthropic` and `codex` are, because the label is written from
    the observed failure and a reader enumerating names of its own can only
    report a plausible absence for the ones it never thought of.

    THE ACCOUNT IS PART OF THE KEY, not a field hanging off a per-vendor
    record: "Records are distinct per provider and credential identity: a newer
    record for one identity neither supersedes nor retires a live record for
    another." Keyed on the vendor alone, four runs meeting one account's
    ceiling within six minutes each retired their predecessor, and a record
    minted a minute later for a DIFFERENT account retired all of them -- while
    every one of those accounts still held its own ceiling. An absent identity
    is itself a key, so a provider-only record and an account-named record of
    one vendor are two records.

    The walk is newest-first, so the operator's early clearance costs one
    branch: a `provider-exhaustion-cleared` line met BEFORE any observation
    means that observation is already retired, and nothing is held for it.
    Meeting it AFTER an unexpired observation is a clearance an operator has
    since re-observed past, so it retires nothing. An EXPIRED observation
    decides nothing either way and the walk continues past it, which is what
    lets an older live record for the same key still answer.
    """
    now = _parse_journal_iso(text=now_iso)
    if journal_path is None or not journal_path.is_file():
        return ()
    live: list[ProviderExhaustionRecord] = []
    decided: set[object] = set()
    for record in reversed(_records(text=journal_path.read_text(encoding="utf-8"))):
        key = (record.get("provider"), _record_identity(record=record))
        if key in decided:
            continue
        if record.get("stage") == _CLEARED_STAGE:
            decided.add(key)
            continue
        parsed = _provider_record(record=record)
        if _parse_journal_iso(text=parsed.record_expires_at) > now:
            decided.add(key)
            live.append(parsed)
    return tuple(live)


def active_provider_exhaustion(
    *,
    provider: str,
    journal_path: Path | None,
    now_iso: str,
) -> ProviderExhaustionRecord | None:
    """The newest unexpired record for ONE named provider, if it holds one.

    Selective by construction: a record naming another vendor is skipped, so a
    provider this dispatch holds no record for is never refused on another
    vendor's ceiling. This is the LEGACY VALVE's own read -- it names the
    provider it is clearing -- and it is a projection of the one walk above
    rather than a second walk, so the valve and the gate cannot disagree about
    what is live.
    """
    for record in live_provider_exhaustions(journal_path=journal_path, now_iso=now_iso):
        if record.provider == provider:
            return record
    return None


def dispatch_provider_exhaustion(
    *,
    journal_path: Path | None,
    now_iso: str,
) -> ProviderExhaustionRecord | None:
    """The newest unexpired legacy record on this journal, whatever it names.

    This is the FACTORY-WIDE question -- "is a provider-exhaustion wait in
    force here at all?" -- which the awareness surface asks because it reports
    a wait rather than deciding one item's admission. The ADMISSION question is
    narrower and has its own read: `covering_provider_exhaustion`, which no
    record answers without covering a candidate the dispatch renders.
    """
    live = live_provider_exhaustions(journal_path=journal_path, now_iso=now_iso)
    return live[0] if live else None


def covering_provider_exhaustion(
    *,
    journal_path: Path | None,
    now_iso: str,
    candidates: tuple[RenderedCandidate, ...] | None,
    projected_identities: frozenset[str],
) -> ProviderExhaustionRecord | None:
    """The newest live record COVERING a candidate and an ACCOUNT this dispatch uses.

    `candidates` is the dispatch's resolved node adapters, projected into the
    candidates they render; the providers this dispatch can be refused on are
    derived from them, which is what replaced the hard-coded vendor tuple
    described at the top of this module.

    `projected_identities` is the SECOND axis, and it is the one a vendor label
    alone cannot express: the accounts this dispatch's own admission
    session-headroom assessment projected for its covered candidates. A record
    naming an account none of them uses covers nothing, which is how a
    credential rotation stops being defeated by records its predecessor minted.

    `None` candidates means the resolution could not be READ, and it is
    deliberately not the empty tuple: an empty set of candidates is an answer
    -- this dispatch renders nothing the record covers -- while an unreadable
    one is the absence of a measurement. A gauge that admitted when blinded
    would turn every unreadable configuration into a pass, so the unreadable
    arm FAILS CLOSED onto the pre-scoping behaviour, where any live record
    refuses.
    """
    for record in live_provider_exhaustions(journal_path=journal_path, now_iso=now_iso):
        if not record_identity_covers_dispatch(
            record_identity=record.credential_identity,
            projected_identities=projected_identities,
        ):
            continue
        if candidates is None or legacy_record_covers_dispatch(
            provider=record.provider, candidates=candidates
        ):
            return record
    return None


def provider_exhaustion_refusal(
    *,
    work_item_id: str,
    journal: _Journal,
    journal_path: Path | None,
    now_iso: str,
    candidates: tuple[RenderedCandidate, ...] | None,
    projected_identities: frozenset[str],
) -> DispatchOutcome | None:
    """Refuse this dispatch when a COVERED provider's ceiling is still held.

    This is the FIRST refusal in the eligibility ladder, so the one thing it
    must not do is refuse an item none of the held allowances could have
    spent: a vendor ceiling is a fact about the factory, but only about the
    part of the factory this item's nodes actually reach. `candidates` is
    therefore the dispatch's own resolved node adapters, projected into the
    candidates they render, and a record covering none of them refuses
    nothing and journals nothing — a refusal line naming a hold the item
    could not have hit is the plausible wrong answer Scenario 60's "A hold on
    one provider does not refuse an item wholly on another" exists to forbid.

    The refusal names the vendor AND THE ACCOUNT from the RECORD — the one that
    actually refused — so an operator reading the journal is told which
    allowance is gone rather than a constant that may name a vendor nothing was
    observed against. The account matters most where the vendor is least
    informative: a factory rotating between accounts of one vendor produces
    refusals whose provider field is identical and whose remedies are not.
    """
    record = covering_provider_exhaustion(
        journal_path=journal_path,
        now_iso=now_iso,
        candidates=candidates,
        projected_identities=projected_identities,
    )
    if record is None:
        return None
    outcome = DispatchOutcome(
        work_item_id=work_item_id,
        status="provider-exhaustion",
        stage="provider-exhaustion",
        pr_number=None,
        merge_sha=None,
        detail=(
            "provider exhaustion refusal: "
            f"provider={record.provider} "
            f"credential_identity={record.credential_identity} "
            f"governing_condition={record.governing_condition} "
            f"record_expires_at={record.record_expires_at}"
        ),
    )
    journal.append(record={"stage": "outcome", "outcome": _outcome_record(outcome=outcome)})
    journal.append(
        record={
            "stage": _REFUSAL_STAGE,
            "work_item_id": work_item_id,
            "provider": record.provider,
            "credential_identity": record.credential_identity,
            "governing_condition": record.governing_condition,
            "record_expires_at": record.record_expires_at,
        }
    )
    return outcome


def _outcome_record(*, outcome: DispatchOutcome) -> dict[str, object]:
    record: dict[str, object] = {
        "work_item_id": outcome.work_item_id,
        "status": outcome.status,
        "stage": outcome.stage,
        "pr_number": outcome.pr_number,
        "merge_sha": outcome.merge_sha,
        "detail": outcome.detail,
        "fabro_run_id": outcome.fabro_run_id,
    }
    return record


def _records(*, text: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in text.splitlines():
        parsed_record = cast("dict[object, object]", json.loads(line))
        record = {str(key): value for key, value in parsed_record.items()}
        if record.get("stage") in {_RECORD_STAGE, _CLEARED_STAGE}:
            records.append(record)
    return records


def _parse_journal_iso(*, text: str) -> datetime:
    return cast("datetime", parse_iso_datetime(text=text.removesuffix("Z") + "+00:00"))


def _provider_record(*, record: dict[str, object]) -> ProviderExhaustionRecord:
    provider = record.get("provider")
    condition = record.get("governing_condition")
    expires_at = record.get("record_expires_at")
    work_item_id = record.get("work_item_id")
    return ProviderExhaustionRecord(
        provider=cast("str", provider),
        governing_condition=cast("str", condition),
        record_expires_at=cast("str", expires_at),
        work_item_id=cast("str", work_item_id),
        credential_identity=_record_identity(record=record),
    )


def _record_identity(*, record: dict[str, object]) -> str | None:
    """The account one journal line names, or `None` when it names none.

    ONE reader for both the parsed record and the liveness walk's key, because
    the two must agree about what a record's account IS: a walk that computed
    the key differently would file a record under one account and report it as
    another, and every surface downstream reads the second.

    A record minted before accounts were named carries no key at all, and one
    minted for a dispatch that projected none carries an explicit null. Both
    are the vendor-wide record the clause keeps effective, so both read as
    `None` rather than as a label matching nothing.
    """
    identity = record.get("credential_identity")
    return identity if isinstance(identity, str) else None
