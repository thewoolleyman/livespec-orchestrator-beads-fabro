"""A dispatch whose account cannot be read is refused, not admitted.

Binds `SPECIFICATION/scenarios.md` "## Scenario 186" case "An unreadable
credential identity fails closed", against the closing sentence of the
credential-identity clause in `SPECIFICATION/contracts.md` section "Dispatcher
admission, WIP cap, and post-merge acceptance": "When a dispatch's projected
credential identity is absent, the record covers it, so that a blinded gauge
fails closed."

THIS IS THE ONE ASSERTION THE REST OF THE FIX ARGUES AGAINST, which is why it
needs its own binding. Every other case here narrows an account-named record so
it stops refusing dispatches it could not have constrained; this one WIDENS it
back onto a dispatch whose own account is unknown. The asymmetry is deliberate
and it is the direction the fleet's standing rule picks: a gauge that admitted
whenever it could not observe its input would turn every unreadable projection
into a pass, and blinding the input is then the cheapest way past the gate.

TWO WAYS TO BE BLIND, and they are different states that owe the same answer.
`absent` is the literal identity `projected_credential_identity` writes when
there is no credential to fingerprint -- a reading was taken and it reports an
absence. An EMPTY projected set is no reading at all: an evaluation that
assessed no covered candidate, or one whose policy was never supplied. Neither
is evidence that this dispatch would have missed the ceiling.

THE CONTROL IS THE READABLE CASE on the same journal, because a predicate that
had simply gone back to refusing everything satisfies both halves above while
undoing the whole fix.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T17:42:00Z"
_LIVE_EXPIRY = "2099-01-01T00:00:00Z"
_EXHAUSTED_ACCOUNT = "1111111111111111"
_ROTATED_ACCOUNT = "2222222222222222"
# The literal `_dispatcher_session_headroom_io.ABSENT_CREDENTIAL_IDENTITY`
# journals when there is no credential to fingerprint. Spelled out here and
# bound to the exported name by the first case below.
_ABSENT = "absent"


def _exhaustion() -> Any:
    return import_module(f"{_PACKAGE}._dispatcher_provider_exhaustion")


def _journal(*, tmp_path: Path, identity: str | None) -> Path:
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    path.write_text(
        json.dumps(
            {
                "at": _NOW,
                "stage": "provider-exhaustion-observed",
                "work_item_id": "bd-observer",
                "provider": "anthropic",
                "credential_identity": identity,
                "governing_condition": "provider_usage_limit",
                "record_expires_at": _LIVE_EXPIRY,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _rendered_anthropic() -> Any:
    schema = import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = import_module(f"{_PACKAGE}._acp_node_adapters")
    coverage = import_module(f"{_PACKAGE}._acp_dispatch_coverage")
    return coverage.RenderedCandidate(
        candidate=schema.AcpCandidate(
            adapter=adapters.AcpAdapter(command="claude-adapter", env={}, args=()),
            identity=schema.AcpCandidateIdentity(
                display_name="built-in Anthropic ACP adapter",
                candidate_key="builtin-anthropic-0000000000000000",
                availability_key="anthropic",
            ),
        ),
        builtin=True,
    )


def _covering(*, path: Path, projected: frozenset[str]) -> Any:
    return _exhaustion().covering_provider_exhaustion(
        journal_path=path,
        now_iso=_NOW,
        candidates=(_rendered_anthropic(),),
        projected_identities=projected,
    )


def test_the_absent_sentinel_is_bound_to_the_identity_the_projection_writes() -> None:
    """The value this file asserts about is the one the projection really writes."""
    headroom_io = import_module(f"{_PACKAGE}._dispatcher_session_headroom_io")

    assert headroom_io.ABSENT_CREDENTIAL_IDENTITY == _ABSENT


def test_an_absent_projected_account_is_refused_by_a_record_naming_any_account(
    tmp_path: Path,
) -> None:
    """Scenario 186: "An unreadable credential identity fails closed"."""
    path = _journal(tmp_path=tmp_path, identity=_EXHAUSTED_ACCOUNT)

    absent = _covering(path=path, projected=frozenset({_ABSENT}))
    assert absent is not None, "a dispatch with no readable account was admitted"
    assert absent.credential_identity == _EXHAUSTED_ACCOUNT
    # An absence beside a readable account is still an absence: part of this
    # dispatch cannot be told apart from the exhausted account, so the record
    # still reaches it.
    mixed = _covering(path=path, projected=frozenset({_ABSENT, _ROTATED_ACCOUNT}))
    assert mixed is not None
    # The control, on the same journal and the same record: a dispatch whose
    # account IS readable and is not the one named is admitted. Without it, a
    # predicate that had gone back to refusing everything would pass above.
    assert _covering(path=path, projected=frozenset({_ROTATED_ACCOUNT})) is None


def test_a_projection_that_was_never_taken_is_refused_the_same_way(
    tmp_path: Path,
) -> None:
    """No reading at all is the absence of a measurement, not an answer.

    An evaluation that assessed no covered candidate -- or one resolved with no
    headroom policy, as wait attention and idle-factory are -- projects the
    empty set. That is not evidence this dispatch would have missed the
    ceiling, so it fails closed exactly as the explicit absence does.
    """
    path = _journal(tmp_path=tmp_path, identity=_EXHAUSTED_ACCOUNT)

    blinded = _covering(path=path, projected=frozenset())
    assert blinded is not None, "a dispatch whose projection was never taken was admitted"
    assert blinded.credential_identity == _EXHAUSTED_ACCOUNT
    # The control: the same empty projection against a record of ANOTHER vendor
    # refuses nothing, so failing closed on the account axis has not been
    # allowed to widen the vendor axis the previous slices scoped.
    codex = tmp_path / "codex"
    codex.mkdir()
    codex_path = codex / "fabro-dispatch-journal.jsonl"
    codex_path.write_text(
        json.dumps(
            {
                "at": _NOW,
                "stage": "provider-exhaustion-observed",
                "work_item_id": "bd-observer",
                "provider": "codex",
                "credential_identity": _EXHAUSTED_ACCOUNT,
                "governing_condition": "provider_usage_limit",
                "record_expires_at": _LIVE_EXPIRY,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert _covering(path=codex_path, projected=frozenset()) is None
