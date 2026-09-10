"""The two chain digests, and the REDACTED structural form of a candidate.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" narrows the existing journal rule for a fallback-enabled node:
journals, traces, events, diagnostics and refusals must store a redacted
structural form -- command and args, env KEY NAMES and their supplying
layers, plus a deterministic digest -- and never raw env values or the
full candidate chain.

WHY TWO DIGESTS AND NOT ONE. They answer different questions and change on
different edits, which is the whole reason later slices can tell a primary
REPLACEMENT from a fallback-only edit:

- The PRIMARY-GENERATION digest covers candidate zero alone. A model
  fallback warning is scoped to it, so replacing the primary retires that
  warning as superseded while editing the tail of the chain must not.
- The FULL-CHAIN digest covers the primary AND every fallback in order. A
  fallback-only edit changes it and leaves the primary generation
  standing, which is exactly the discrimination the warning lifecycle
  needs.

WHY THE DIGEST INPUT INCLUDES ENV VALUES WHILE THE RECORD DOES NOT. A
digest is one-way; a record is read. Hashing the values is what makes the
digest change when a base URL or a model pin moves, and printing them is
what the redaction rule forbids. Those are not in tension -- they are the
reason the digest exists at all.

DETERMINISM IS CONTRACTUAL, so the canonical form sorts every mapping key
and renders with separators fixed and non-ASCII escaped. Two dispatches
resolving the same chain must produce the same digest on any machine, or
nothing downstream can compare one run's generation with another's.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import ResolvedAcpNode

__all__: list[str] = [
    "candidate_fingerprint",
    "full_chain_digest",
    "primary_generation_digest",
    "redacted_structural_record",
]

_DIGEST_LENGTH = 32


def candidate_fingerprint(*, candidate: AcpCandidate) -> dict[str, object]:
    """The canonical, order-stable value one candidate digests to."""
    identity = candidate.identity
    return {
        "args": list(candidate.adapter.args),
        "command": candidate.adapter.command,
        "env": {key: candidate.adapter.env[key] for key in sorted(candidate.adapter.env)},
        "identity": None if identity is None else list(identity.pair),
        "pricing": None if candidate.pricing is None else candidate.pricing.model,
        "signatures": [
            [signature.source, signature.cause, signature.scope, signature.hold_key or ""]
            for signature in candidate.signatures
        ],
    }


def primary_generation_digest(*, primary: AcpCandidate) -> str:
    """The stable fingerprint of candidate zero alone."""
    return _digest(payload={"primary": candidate_fingerprint(candidate=primary)})


def full_chain_digest(*, primary: AcpCandidate, fallbacks: tuple[AcpCandidate, ...]) -> str:
    """The stable fingerprint of the whole ordered chain.

    Fallbacks are digested IN CONFIGURED ORDER rather than sorted, because
    order is semantic here: the same two candidates swapped are a different
    chain, and a digest that could not tell them apart would report an
    operator's re-prioritisation as no change at all.
    """
    return _digest(
        payload={
            "primary": candidate_fingerprint(candidate=primary),
            "fallbacks": [candidate_fingerprint(candidate=entry) for entry in fallbacks],
        }
    )


def redacted_structural_record(
    *,
    resolved: ResolvedAcpNode,
    primary_generation: str,
    full_chain: str,
    fallback_count: int,
) -> dict[str, object]:
    """The structural record a journal, trace, event or refusal may carry.

    It reports the primary's command and args, the env KEY NAMES with the
    layer that supplied each, both digests, and how many fallbacks stand
    behind it -- deliberately NOT the fallbacks themselves. A reader can
    still tell a workflow default from a repository override and can still
    compare one run's chain with another's, without the record ever
    carrying an env value or the chain it would take to reconstruct one.
    """
    adapter = resolved.adapter
    return {
        "command": adapter.command,
        "args": list(adapter.args),
        "env_keys": sorted(adapter.env),
        "layers": {
            "command": resolved.command_layer,
            "args": resolved.args_layer,
            "env": dict(sorted(resolved.env_layers.items())),
        },
        "primary_generation_digest": primary_generation,
        "full_chain_digest": full_chain,
        "fallback_count": fallback_count,
    }


def _digest(*, payload: Mapping[str, object]) -> str:
    """A deterministic, truncated SHA-256 over the canonical JSON payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
