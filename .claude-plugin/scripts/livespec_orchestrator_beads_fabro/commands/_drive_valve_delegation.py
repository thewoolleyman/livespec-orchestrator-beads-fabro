"""Delegated valve authority: verifying a `delegate:<name>` press, and recording it.

The delegated-valve-authority paragraph of the journal invoker attribution
contract in `SPECIFICATION/contracts.md` makes a maintainer's delegation of the
human valves first-class. A press asserts `--invoker delegate:<delegate-name>`
and names the delegation it acts under with `--delegation <ref>`; `drive`
admits it only when the ref matches a committed `dispatcher.valve_delegations`
entry for exactly that delegate, and only on the delegable valve allowlist.

WHY THE GRANT LIVES IN COMMITTED CONFIG. A delegation an agent could name at
press time is a delegation an agent could invent. The setting is read only from
the committed `.livespec.jsonc` and is deliberately absent from the
API-configurable key manifest, so granting one is a reviewable change in git
history and a press can only CITE a grant, never create one.

WHY THE ALLOWLIST IS CODE AND NOT CONFIG. The maintainer's grant excludes
credential, irreversible and outward-facing acts. The allowlist is that
exclusion made mechanical, and a config entry able to widen it would turn a
reviewable grant into a way to reach the merge hold or the factory-safety
opt-out.

IT FAILS CLOSED. An unreadable setting verifies no press, a half-delegated
press (the role without the ref, or the ref without the role) is refused, and
every refusal precedes the first store, journal or ledger write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    DELEGATE_ROLE,
    DelegationGrant,
    InvokerIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    read_dispatcher_config_value,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_grammar import (
    parse_human_valve_action,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import valve_refusal
from livespec_orchestrator_beads_fabro.store import append_work_item_comment

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "DELEGABLE_VALVES",
    "DELEGATED_PRESS_MARKER",
    "DelegationVerdict",
    "record_delegated_press",
    "verify_delegation",
]

# The delegable valve allowlist, verbatim from the contract. Nothing else — the
# factory-safety opt-out and its clearance, the merge hold, the policy, cap,
# queue and workflow-scope edits, and every dispatch — is delegable.
DELEGABLE_VALVES: frozenset[str] = frozenset(
    {"resolve-blocked", "approve", "accept", "reject", "release-spec-tier"}
)
DELEGATED_PRESS_MARKER = "livespec-delegated-valve-press"

_SETTING = "valve_delegations"
_ENTRY_FIELDS = ("ref", "delegate", "grantor", "record")
_HUMAN_PREFIX = "human:"
_ROLE_SEPARATOR = ":"


@dataclass(frozen=True, kw_only=True)
class DelegationVerdict:
    """The verifier's answer: a refusal payload, or the identity to press under.

    Exactly one of the two is set. `identity` is the invocation's own identity
    when the press is not delegated at all, and that identity carrying its
    verified `DelegationGrant` when it is.
    """

    refusal: dict[str, Any] | None
    identity: InvokerIdentity | None


def verify_delegation(
    *, repo: Path, action_id: str, identity: InvokerIdentity, delegation: str | None
) -> DelegationVerdict:
    """Grade one press's delegation claim before anything reads toward a write."""
    ref = None if delegation is None else delegation.strip() or None
    role, name = _role_and_name(invoker=identity.invoker)
    delegated_role = role == DELEGATE_ROLE
    if not delegated_role and ref is None:
        return DelegationVerdict(refusal=None, identity=identity)
    if not delegated_role or ref is None:
        return _refused(
            aid=action_id,
            err="delegation-incomplete",
            identity=identity,
            ref=ref,
            why=(
                f"a delegated press asserts --invoker {DELEGATE_ROLE}:<delegate-name> AND "
                "names --delegation <ref>; this press carried only one of the two"
            ),
        )
    verb = _verb(action_id=action_id)
    if verb not in DELEGABLE_VALVES:
        return _refused(
            aid=action_id,
            err="delegation-not-permitted",
            identity=identity,
            ref=ref,
            why=(
                "the maintainer's delegation never covers this action; the delegable "
                f"valves are {', '.join(sorted(DELEGABLE_VALVES))}"
            ),
        )
    grant, why = _grant_for(repo=repo, ref=ref, delegate=name)
    if grant is None:
        return _refused(
            aid=action_id, err="delegation-unverified", identity=identity, ref=ref, why=why
        )
    return DelegationVerdict(
        refusal=None,
        identity=InvokerIdentity(
            invoker=identity.invoker, invoker_source=identity.invoker_source, delegation=grant
        ),
    )


def record_delegated_press(
    *, config: StoreConfig, identity: InvokerIdentity, result: dict[str, Any]
) -> dict[str, Any]:
    """Append the delegated-press ledger comment to a GREEN press; annotate the result.

    A refused press writes nothing, so a non-green result passes through
    untouched. The comment is the ledger's plain statement that the delegate,
    not the human who granted the delegation, pressed this valve.
    """
    grant = identity.delegation
    item_id = result.get("work_item_ref")
    if grant is None or result.get("status") != "green" or not isinstance(item_id, str):
        return result
    append_work_item_comment(
        path=config,
        work_item_id=item_id,
        body=(
            f"{DELEGATED_PRESS_MARKER}\n\n"
            f"action: {result.get('action_id')}\n"
            f"pressed by: {identity.invoker} (via {identity.invoker_source})\n"
            f"under maintainer delegation: {grant.ref}\n"
            f"granted by: {grant.grantor}\n"
            f"grant recorded at: {grant.record}\n\n"
            "The delegate acted under the maintainer's recorded delegation; this is "
            "not the maintainer's personal press."
        ),
    )
    return result | {"delegation": grant.as_record()}


def _verb(*, action_id: str) -> str | None:
    parsed = parse_human_valve_action(action_id=action_id)
    return None if parsed is None else parsed[0]


def _role_and_name(*, invoker: str) -> tuple[str, str]:
    role, separator, name = invoker.partition(_ROLE_SEPARATOR)
    if separator == "" or name.strip() == "":
        return ("", "")
    return (role, name.strip())


def _grant_for(*, repo: Path, ref: str, delegate: str) -> tuple[DelegationGrant | None, str]:
    """The committed grant for (ref, delegate), or `None` with the reason why not."""
    read = read_dispatcher_config_value(cwd=repo, key=_SETTING)
    if not is_successful(read):
        detail = unsafe_perform_io(read.failure()).detail
        return (None, f"dispatcher.{_SETTING} is unreadable ({detail}), so it verifies no press")
    raw = unsafe_perform_io(read.unwrap())
    entries, problem = _entries(raw=raw)
    if problem is not None:
        return (None, f"dispatcher.{_SETTING} is unreadable ({problem}), so it verifies no press")
    for entry in entries:
        if entry.ref == ref and entry.delegate == delegate:
            return (DelegationGrant(ref=entry.ref, grantor=entry.grantor, record=entry.record), "")
    if any(entry.ref == ref for entry in entries):
        return (None, f"committed delegation {ref} does not authorize delegate {delegate!r}")
    return (None, f"no committed dispatcher.{_SETTING} entry carries ref {ref}")


@dataclass(frozen=True, kw_only=True)
class _Entry:
    ref: str
    delegate: str
    grantor: str
    record: str


def _entries(*, raw: object) -> tuple[tuple[_Entry, ...], str | None]:
    """Every committed entry, or a problem that makes the WHOLE setting unreadable."""
    if raw is None:
        return ((), None)
    if not isinstance(raw, list):
        return ((), "it must be a list")
    entries: list[_Entry] = []
    for index, node in enumerate(cast("list[object]", raw)):
        entry = _entry(node=node)
        if entry is None:
            return (
                (),
                (
                    f"entry {index} must carry non-empty strings {', '.join(_ENTRY_FIELDS)} "
                    f"and a named {_HUMAN_PREFIX}<name> grantor"
                ),
            )
        entries.append(entry)
    return (tuple(entries), None)


def _entry(*, node: object) -> _Entry | None:
    if not isinstance(node, dict):
        return None
    fields = cast("dict[str, object]", node)
    values = [fields.get(name) for name in _ENTRY_FIELDS]
    if not all(isinstance(value, str) and value.strip() for value in values):
        return None
    ref, delegate, grantor, record = (cast("str", value).strip() for value in values)
    if not grantor.startswith(_HUMAN_PREFIX) or grantor == _HUMAN_PREFIX:
        return None
    return _Entry(ref=ref, delegate=delegate, grantor=grantor, record=record)


def _refused(
    *, aid: str, err: str, identity: InvokerIdentity, ref: str | None, why: str
) -> DelegationVerdict:
    return DelegationVerdict(
        refusal=valve_refusal(
            aid=aid,
            err=err,
            msg=(
                f"{aid} refused: invoker {identity.invoker!r} with delegation "
                f"{ref if ref is not None else '(none)'}: {why}. Nothing was written."
            ),
        ),
        identity=None,
    )
