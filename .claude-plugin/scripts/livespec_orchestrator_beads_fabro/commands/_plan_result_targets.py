"""The five typed targets a required result may name, and the reference carrying one.

The shared-authoritative-result-reader clause of `SPECIFICATION/contracts.md`
fixes the grammar: a required result is a typed reference containing a canonical
repository identity and exactly one kind-specific target — `item_status` (item id
and expected status), `item_comment` (item id and exact marker),
`pull_request_state` (PR number and expected state), `verified_proof` (subject
id, build identity and assertion identifiers), or `file_on_branch` (branch, path
and expected Git blob id).

This module is the GRAMMAR; `_plan_result_reference` is the parse that admits a
value into it. The split is the usual one in this tree — the types carry no
refusals and the parse carries nothing else — and it matters here because the
adapters import the targets and never the parse, so a parse living beside them
would pull the whole refusal ladder into every reader.

WHY EVERY TARGET CARRIES AN `identity` RATHER THAN LETTING EACH ADAPTER RENDER
ONE. The same clause requires every observation to report target identity, and an
adapter that composed its own would compose a DIFFERENT one on the satisfied arm
and the unobservable arm — which is precisely where an operator compares two
observations of one obligation to decide whether the target moved or the
instrument did. One rendering per kind, owned by the kind, cannot drift that way.

WHY THE KIND RIDES ON THE TARGET AS A `Literal` DEFAULT. The reader dispatches on
it, and a union whose members carry no discriminator forces every consumer to
re-derive the kind by `isinstance`, which is the shape that silently stops
covering a kind added later. The literal defaults are spelled out rather than
composed from the module constants because a `Literal[...]` annotation admits
only a literal, and the constants exist for the parse and the renderings.

WHY `verified_proof` TAKES ASSERTION IDENTIFIERS AS A TUPLE. The clause names
assertion identifiers, plural, and a typed proof record grades one assertion at a
time: a single identifier would let a partially-reproduced record satisfy a result
whose scope the record never covered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

__all__: list[str] = [
    "FILE_ON_BRANCH_KIND",
    "ITEM_COMMENT_KIND",
    "ITEM_STATUS_KIND",
    "PULL_REQUEST_STATE_KIND",
    "RESULT_KINDS",
    "VERIFIED_PROOF_KIND",
    "FileOnBranchTarget",
    "ItemCommentTarget",
    "ItemStatusTarget",
    "PullRequestStateTarget",
    "ResultReference",
    "ResultReferenceRefusal",
    "ResultTarget",
    "VerifiedProofTarget",
]

ITEM_STATUS_KIND = "item_status"
ITEM_COMMENT_KIND = "item_comment"
PULL_REQUEST_STATE_KIND = "pull_request_state"
VERIFIED_PROOF_KIND = "verified_proof"
FILE_ON_BRANCH_KIND = "file_on_branch"

# The CLOSED set, in the order the clause enumerates it. Closed is the whole
# point: the same clause says arbitrary shell predicates MUST NOT be accepted as
# result references, and a closed enumeration is what makes that a property of the
# grammar rather than a scan for shell-looking strings.
RESULT_KINDS: tuple[str, ...] = (
    ITEM_STATUS_KIND,
    ITEM_COMMENT_KIND,
    PULL_REQUEST_STATE_KIND,
    VERIFIED_PROOF_KIND,
    FILE_ON_BRANCH_KIND,
)


@dataclass(frozen=True, kw_only=True)
class ItemStatusTarget:
    """One ledger item expected to stand at one lifecycle status."""

    item_id: str
    status: str
    kind: Literal["item_status"] = "item_status"

    @property
    def identity(self) -> str:
        """The target identity every observation of this target reports."""
        return f"{self.kind} {self.item_id} status {self.status}"


@dataclass(frozen=True, kw_only=True)
class ItemCommentTarget:
    """One ledger item expected to carry one EXACT marker in a comment.

    The clause is explicit that this kind proves the least of the five: comment
    marker satisfaction proves only the requested marker's presence and must not
    stand in for completed implementation or verified proof. The narrowing is
    carried in the observation's own detail rather than left to whoever reads the
    result, because a satisfied observation is the thing that gets quoted onward.
    """

    item_id: str
    marker: str
    kind: Literal["item_comment"] = "item_comment"

    @property
    def identity(self) -> str:
        """The target identity every observation of this target reports."""
        return f"{self.kind} {self.item_id} marker {self.marker!r}"


@dataclass(frozen=True, kw_only=True)
class PullRequestStateTarget:
    """One pull request expected to stand at one forge state."""

    number: int
    state: str
    kind: Literal["pull_request_state"] = "pull_request_state"

    @property
    def identity(self) -> str:
        """The target identity every observation of this target reports."""
        return f"{self.kind} #{self.number} state {self.state}"


@dataclass(frozen=True, kw_only=True)
class VerifiedProofTarget:
    """One subject's typed Proof of Done record, scoped to named assertions.

    `build` is the build identity the record must name — the release tag or the
    default-branch commit the host-leg clause calls the containment ref, never the
    installed build identifier, which that clause records without verifying.
    """

    subject_id: str
    build: str
    assertions: tuple[str, ...]
    kind: Literal["verified_proof"] = "verified_proof"

    @property
    def identity(self) -> str:
        """The target identity every observation of this target reports."""
        return f"{self.kind} {self.subject_id} build {self.build} assertions {len(self.assertions)}"


@dataclass(frozen=True, kw_only=True)
class FileOnBranchTarget:
    """One path on one REMOTE branch, expected to hold one Git blob.

    The clause requires the comparison to be against the remote branch's blob
    identity rather than a stale checkout or mere path existence, which is why the
    expected value is a blob id and not a flag or a content excerpt: a path that
    exists and a path that holds the requested bytes are different facts, and only
    one of them is the result.
    """

    branch: str
    path: str
    blob: str
    kind: Literal["file_on_branch"] = "file_on_branch"

    @property
    def identity(self) -> str:
        """The target identity every observation of this target reports."""
        return f"{self.kind} {self.branch}:{self.path} blob {self.blob}"


ResultTarget: TypeAlias = (
    ItemStatusTarget
    | ItemCommentTarget
    | PullRequestStateTarget
    | VerifiedProofTarget
    | FileOnBranchTarget
)


@dataclass(frozen=True, kw_only=True)
class ResultReference:
    """A canonical repository identity plus exactly one typed target."""

    repo: str
    target: ResultTarget

    @property
    def identity(self) -> str:
        """Repository and target together, as one line an operator can compare."""
        return f"{self.repo} {self.target.identity}"


@dataclass(frozen=True, kw_only=True)
class ResultReferenceRefusal:
    """Why one value is not a result reference at all.

    Deliberately a value rather than an exception. A malformed reference is an
    UNOBSERVABLE result under the clause — malformed evidence must be
    `unobservable`, never satisfaction or a confident negative — so the refusal
    has to travel to the reader as data it can turn into an observation, not as a
    control-flow escape the reader would have to catch outside this tree's one
    permitted effect boundary.

    `repo` is the repository identity the refused value DID name, where the
    refusal happened after that field was read, and the empty string where it did
    not. The clause requires every observation to report its repository, and a
    refusal that dropped a perfectly good identity would make the resulting
    unobservable reading unattributable to the obligation that produced it.
    """

    detail: str
    repo: str = ""
