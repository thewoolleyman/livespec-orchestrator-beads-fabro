"""WHICH of one DISPATCH's rendered candidates a legacy provider record covers.

Binds the dispatch-scoped half of the legacy-record clause in
`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -- "Legacy provider-only records remain readable, clearable by the
legacy valve, and effective until retirement against built-in candidates whose
compatibility alias names that provider plus identity-less legacy candidates,
which every live legacy record covers. Explicitly identified candidates MUST
NOT be broadened to unrelated identities." -- together with the Scenario 60
scenario it serves: "A hold on one provider does not refuse an item wholly on
another".

`_acp_hold_coverage.legacy_record_covers_candidate` already answers that
question for ONE candidate and is covered by `test_acp_hold_lifecycle`. What is
asserted here is the question the ADMISSION GATE actually asks, which the
per-candidate predicate cannot answer on its own: does this record cover
ANYTHING the dispatch's resolved ACP nodes render? The gate this replaces had
no candidate set at all -- it iterated a hard-coded vendor tuple -- so the
discriminating case is a dispatch every one of whose candidates sits in a
domain the record does not name, which the old gate refused and the new one
must admit.

TWO CONTROLS CARRY THE WEIGHT, because each is the direction an
almost-correct implementation gets backwards:

- An operator who chose the vendor's own word as an `availability_key` has NOT
  opted into that vendor's legacy blanket. `builtin` is the provenance fact
  the caller carries, never a reading of how the key is spelled, so a
  dispatch of operator-identified candidates is covered by nothing.
- An IDENTITY-LESS candidate is covered by EVERY live record, so one such
  candidate anywhere in the dispatch is enough to keep the record effective.
  A reading that keyed coverage on the record's provider alone would report
  the opposite for a vendor none of the dispatch's keys mention.

Everything is PURE: chains are built in memory, no file is read and no
adapter is launched.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_acp_dispatch_coverage"

_BUILTIN_CODEX = ("codex", "builtin-codex-0000000000000000")
_BUILTIN_ANTHROPIC = ("anthropic", "builtin-anthropic-0000000000000000")
_BUILTIN_PAIRS = frozenset({_BUILTIN_CODEX, _BUILTIN_ANTHROPIC})


def _coverage() -> Any:
    """Import the module under test, proving its file exists first."""
    assert (_COMMANDS / f"{_MODULE}.py").is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _candidate(*, pair: tuple[str, str] | None) -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    identity = (
        None
        if pair is None
        else schema.AcpCandidateIdentity(
            display_name="candidate",
            candidate_key=pair[1],
            availability_key=pair[0],
        )
    )
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
        identity=identity,
    )


def _chain(*, node: str, primary: Any, fallbacks: tuple[Any, ...] = ()) -> Any:
    resolution = importlib.import_module(f"{_PACKAGE}._acp_chain_resolution")
    return resolution.ResolvedAcpChain(
        node=node,
        primary=primary,
        fallbacks=fallbacks,
        enabled=bool(fallbacks),
        primary_generation="generation",
        full_chain="chain",
        redacted={},
    )


def test_a_legacy_record_covers_a_builtin_alias_and_every_identity_less_adapter() -> None:
    """The blanket is deliberately wide: one uncovered node does not clear it."""
    coverage = _coverage()
    chains = {
        "implement": _chain(node="implement", primary=_candidate(pair=_BUILTIN_CODEX)),
        "pr": _chain(node="pr", primary=_candidate(pair=None)),
    }

    rendered = coverage.rendered_dispatch_candidates(chains=chains, builtin_pairs=_BUILTIN_PAIRS)

    assert [entry.builtin for entry in rendered] == [True, False]
    # The built-in's compatibility alias names "codex", so the codex record
    # covers it; the identity-less adapter keeps the v107 conservative
    # posture, so EVERY live record covers it -- including a vendor no key in
    # this dispatch mentions.
    assert coverage.legacy_record_covers_dispatch(provider="codex", candidates=rendered)
    assert coverage.legacy_record_covers_dispatch(provider="anthropic", candidates=rendered)


def test_a_legacy_record_leaves_explicitly_identified_other_identities_uncovered() -> None:
    """Scenario 60: a hold on one provider cannot refuse a dispatch outside it."""
    coverage = _coverage()
    chains = {
        "implement": _chain(
            node="implement",
            primary=_candidate(pair=("anthropic", "claude-acp/anthropic/claude-opus-5")),
            fallbacks=(_candidate(pair=_BUILTIN_ANTHROPIC),),
        ),
        # An operator who spelled their own key "codex" has not opted into
        # the codex vendor blanket: identity is never inferred from spelling.
        "pr": _chain(node="pr", primary=_candidate(pair=("codex", "my-own-router"))),
    }

    rendered = coverage.rendered_dispatch_candidates(chains=chains, builtin_pairs=_BUILTIN_PAIRS)

    # A node's FALLBACKS are rendered candidates too, so the dispatch's
    # candidate set is three, not two.
    assert len(rendered) == 3
    assert not coverage.legacy_record_covers_dispatch(provider="codex", candidates=rendered)
    # The built-in anthropic fallback IS covered by its own vendor's record,
    # which is the control proving the negative above is scoping and not an
    # instrument that cannot return a hit.
    assert coverage.legacy_record_covers_dispatch(provider="anthropic", candidates=rendered)
