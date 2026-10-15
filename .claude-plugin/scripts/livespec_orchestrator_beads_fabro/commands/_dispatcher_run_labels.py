"""The run labels one dispatch stamps beside its correlation triple.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" requires availability evidence to be discoverable host-wide from
the factory's NATIVE run records, and requires each recorded attempt to
identify its resolved factory, repository, run, node attempt and candidate
entitlement. Two of those five are already named: the correlation triple of
section "Dispatch trace correlation" carries the factory, and the engine
mints the run id itself. This module adds the two the engine cannot know --
WHICH repository dispatched, and WHICH candidate entitlement each ACP node
was rendered against.

WHY LABELS RATHER THAN A SIDECAR. The same section forbids any hold
sidecar file, cache or store, and requires hold observations to stay
reconstructible after a repository-local dispatch journal is removed. A run
label is the FACTORY's own record, so an attempt outlives both this host's
journal and this repository's checkout, and a sibling repository reads it
without a peer list.

WHY AN ENTITLEMENT KEY MAY BE DIGESTED RATHER THAN DROPPED. An
`availability_key` is OPAQUE by contract -- a repository may name an
account domain, a router, or a shared team allowance -- so nothing
constrains it to the engine's label alphabet, and section "Dispatch trace
correlation"'s leave-an-unpassable-value-out rule would then silently erase
the very entitlement the evidence is about. A key the engine would refuse is
therefore carried as a domain-separated SHA-256 digest OF THE KEY, marked
`sha256:` so a reader can tell an encoded value from a verbatim one at a
glance. The digest reads NOTHING but the key: two repositories dispatching
the same `(availability_key, candidate_key)` pair render byte-identical
label values with neither one's configuration consulted, which is what
makes the host-wide join possible at all. An encoding that salted on the
repository, or that mapped the key through a configured table, would
produce a perfectly well-formed label per repository and no join between
them.

THE REPOSITORY LABEL IS NOT DIGESTED, and the asymmetry is deliberate. It
is a name this fleet chooses rather than an opaque one a candidate
declares, so section "Dispatch trace correlation"'s rule applies to it
unchanged: a value the engine would refuse costs its label, never the
dispatch.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import is_identifier_shaped

__all__: list[str] = [
    "AVAILABILITY_LABEL_SUFFIX",
    "CANDIDATE_LABEL_DIGEST_DOMAIN",
    "CANDIDATE_LABEL_DIGEST_PREFIX",
    "CANDIDATE_LABEL_SUFFIX",
    "NODE_LABEL_PREFIX",
    "REPOSITORY_LABEL_KEY",
    "candidate_label_value",
    "dispatch_run_label_pairs",
]

# The label key naming the repository one dispatch ran for. Dotted and
# `livespec.`-prefixed like every other key this Dispatcher writes, so a
# receiver allowlist can key on the prefix rather than on a list of names.
REPOSITORY_LABEL_KEY = "livespec.repository"

# One ACP node's two entitlement labels. `livespec.acp.<node>.availability`
# names WHOSE allowance that node's rendered candidate would spend;
# `livespec.acp.<node>.candidate` names WHAT it would run. They are two keys
# rather than one joined value because a domain hold is scoped by the
# availability key ALONE, so a query for "every attempt that spent this
# account" must not have to take a pair apart to ask it.
NODE_LABEL_PREFIX = "livespec.acp"
AVAILABILITY_LABEL_SUFFIX = "availability"
CANDIDATE_LABEL_SUFFIX = "candidate"

# The digest domain and the marker that announces an encoded value. The
# domain is a constant of THIS encoding rather than of any repository,
# which is exactly what makes two repositories' digests of one key equal.
CANDIDATE_LABEL_DIGEST_DOMAIN = "livespec.acp.candidate.label"
CANDIDATE_LABEL_DIGEST_PREFIX = "sha256:"
# Half of SHA-256 -- the same truncation the dispatch span's trace id takes,
# and for the same reason: collisions are permitted, and 32 hexadecimal
# digits beside the 7-byte marker is 39 bytes, so an encoded value can never
# approach the engine's 128-byte ceiling however long the key was.
_CANDIDATE_LABEL_DIGEST_HEX_DIGITS = 32


def candidate_label_value(*, key: str) -> str:
    """One entitlement key as a label value: verbatim, or its marked digest.

    A key the engine would admit rides verbatim, because an operator reading
    `livespec.acp.implement.availability=anthropic.com` off a run row should
    not have to resolve a digest to learn which account it names. Everything
    else -- an opaque router token, a key carrying a slash or a space, a key
    over the byte ceiling -- is encoded, so no entitlement is ever silently
    absent from the evidence.
    """
    if is_identifier_shaped(value=key):
        return key
    digest = hashlib.sha256(f"{CANDIDATE_LABEL_DIGEST_DOMAIN}:{key}".encode()).hexdigest()
    return f"{CANDIDATE_LABEL_DIGEST_PREFIX}{digest[:_CANDIDATE_LABEL_DIGEST_HEX_DIGITS]}"


def dispatch_run_label_pairs(*, repo: Path, acp_nodes: AcpNodeResolution | None) -> tuple[str, ...]:
    """The `KEY=VALUE` label pairs this dispatch carries beside the triple.

    Nodes are emitted in SORTED order so one configuration renders one
    argv, which is what lets two dispatch records be compared byte for byte.

    `acp_nodes` is None for an invocation that resolved no adapters at all
    -- the reconcile and check subcommands reach the launch seam with a
    Namespace that never carried one, and so does the hermetic tier. Such a
    dispatch carries the repository label alone rather than an invented
    entitlement for a node nothing resolved.
    """
    pairs: list[str] = []
    repository = repo.name
    if is_identifier_shaped(value=repository):
        pairs.append(f"{REPOSITORY_LABEL_KEY}={repository}")
    if acp_nodes is not None:
        pairs.extend(_candidate_pairs(candidates=acp_nodes.candidates))
    return tuple(pairs)


def _candidate_pairs(*, candidates: Mapping[str, AcpCandidateIdentity]) -> tuple[str, ...]:
    """Both entitlement labels for every node that resolved an identity."""
    pairs: list[str] = []
    for node in sorted(candidates):
        identity = candidates[node]
        availability = candidate_label_value(key=identity.availability_key)
        candidate = candidate_label_value(key=identity.candidate_key)
        pairs.append(f"{NODE_LABEL_PREFIX}.{node}.{AVAILABILITY_LABEL_SUFFIX}={availability}")
        pairs.append(f"{NODE_LABEL_PREFIX}.{node}.{CANDIDATE_LABEL_SUFFIX}={candidate}")
    return tuple(pairs)
