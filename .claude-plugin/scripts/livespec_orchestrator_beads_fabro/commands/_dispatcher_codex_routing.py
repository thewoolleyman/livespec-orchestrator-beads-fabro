"""Whether one dispatch routes ANY node to the Codex agent.

The host Codex credential is used in three places on the dispatch path -- the
pre-claim freshness gate, the post-claim overlay leg that grades it again and
stamps the sandbox's credential-use deadline, and the in-sandbox guard that
enforces that deadline. Each applied unconditionally, so a dispatch every one
of whose nodes resolves to `claude-acp` was still refused as the Codex token
aged and still had every node timeout capped by the sum the freshness floor
takes. This module is the ONE answer all three scope themselves by, resolved
once per pass, so they cannot disagree about which dispatches are protected.

WHAT COUNTS AS ROUTING TO CODEX, and every arm but the last is FAIL-CLOSED:

- A resolved candidate whose `candidate_key` NAMES the `codex-acp` agent. The
  key is the derived `<agent>/<provider>/<model>` triple
  (`_acp_structured_identity`), so the agent id leads it.
- A resolved candidate carrying NO identity. That is the conservative legacy
  posture -- an arbitrary adapter this build did not render -- and nothing in
  it says which agent it launches, so it may well be Codex.
- A dispatch whose candidates CANNOT BE RESOLVED. `resolve_dispatch_candidates`
  answers `None` for an unreadable resolution, which is the absence of a
  measurement rather than an answer about candidates; a dispatch nobody could
  observe keeps exactly the protection it had before this module existed.

A KEY IS READ FOR WHAT IT NAMES, NEVER FOR A WORD SPELLED INSIDE IT. The match
is the agent id as the key's leading segment, not a substring: the identity
triple is overridable per field, and an operator who happened to put the
agent's own word in the middle of their key has not declared a Codex launch.
This is `_acp_dispatch_coverage`'s rule about `builtin` one level on -- that
module refuses to infer provenance from spelling for exactly the same reason,
and the direction the two guard is the same one, a protection broadened onto
an identity that never asked for it.

AN EMPTY SET IS THE UNREADABLE ARM, NOT A THIRD CASE, and it is folded into it
deliberately rather than passed through to the key scan.
`resolve_dispatch_candidates` says so in as many words -- "AN EMPTY RESOLUTION
IS UNREADABLE, NOT EMPTY" -- because a workflow declaring no adapter input for
any node overrides nothing and runs whatever the graph itself bakes in, so its
domains are real but invisible from here. Reaching the key scan with an empty
set would report "no candidate names Codex", which is the same sentence as "no
candidate was observed" only to a reader who has stopped failing closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import CODEX_AGENT_ID
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_dispatch_candidates,
)

__all__: list[str] = [
    "CodexRouting",
    "codex_routing_for_candidates",
    "codex_routing_for_dispatch",
]

# The key segment separator the derived identity triple uses. A key equal to the
# bare agent id names it too, which is why both forms are tested.
_KEY_SEGMENT_SEPARATOR = "/"


@dataclass(frozen=True, kw_only=True)
class CodexRouting:
    """Whether this dispatch routes any node to Codex, and what decided it.

    `detail` is carried rather than re-derived by each consumer because the
    dispatch journal has to NAME the routing that scoped the gate away: a record
    saying only that the gate was skipped cannot be checked against the dispatch
    it describes, and the three surfaces that read this value would each have to
    word the same measurement for themselves.
    """

    routes_codex: bool
    detail: str


def codex_routing_for_candidates(
    *, candidates: tuple[RenderedCandidate, ...] | None
) -> CodexRouting:
    """Grade one dispatch's rendered candidates, fail-closed on every absence.

    `candidates` is what `resolve_dispatch_candidates` returned: every candidate
    this repository's resolved ACP nodes render, in node order, or `None` when
    the resolution could not be read. An EMPTY tuple takes the same arm as
    `None` -- see the module docstring on why an empty resolution is unreadable
    rather than empty.
    """
    if not candidates:
        return CodexRouting(
            routes_codex=True,
            detail=(
                "this dispatch's ACP candidates could not be resolved, so which "
                "agent each node launches was never observed"
            ),
        )
    keys: list[str] = []
    unidentified = 0
    for rendered in candidates:
        identity = rendered.candidate.identity
        if identity is None:
            unidentified += 1
        else:
            keys.append(identity.candidate_key)
    if unidentified:
        return CodexRouting(
            routes_codex=True,
            detail=(
                f"{unidentified} of this dispatch's {len(candidates)} resolved ACP "
                "candidates carry no identity, so the agent each launches cannot "
                "be read"
            ),
        )
    codex_keys = [key for key in keys if _names_codex_agent(key=key)]
    if codex_keys:
        return CodexRouting(
            routes_codex=True,
            detail=(
                f"resolved ACP candidate keys naming the {CODEX_AGENT_ID} agent: "
                f"{', '.join(sorted(set(codex_keys)))}"
            ),
        )
    return CodexRouting(
        routes_codex=False,
        detail=(
            f"no resolved ACP candidate key names the {CODEX_AGENT_ID} agent; "
            f"resolved candidate keys: {', '.join(sorted(set(keys)))}"
        ),
    )


def codex_routing_for_dispatch(*, repo: Path) -> CodexRouting:
    """The routing the dispatch `repo`'s resolved ACP nodes would run.

    The IO half, kept beside the rule that grades it so "does this dispatch
    route to Codex" is answered in one place. The resolution itself is
    `_dispatcher_acp_preflight`'s, which is where every read of a repository's
    node adapters already lives; a reader of its own here would be a second
    reading of the same files that could not be proven to agree with the first,
    and the disagreement would be invisible because both produce a well-formed
    candidate set.
    """
    return codex_routing_for_candidates(candidates=resolve_dispatch_candidates(repo=repo))


def _names_codex_agent(*, key: str) -> bool:
    """Whether `key`'s leading segment IS the Codex agent id.

    A segment test rather than a substring test: see the module docstring on why
    a vendor word spelled inside an operator's key is not a declaration.
    """
    return key == CODEX_AGENT_ID or key.startswith(f"{CODEX_AGENT_ID}{_KEY_SEGMENT_SEPARATOR}")
