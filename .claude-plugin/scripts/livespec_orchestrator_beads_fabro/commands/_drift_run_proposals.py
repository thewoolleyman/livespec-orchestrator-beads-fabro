"""The drift-origin proposed change: its document, where it rests, and which exist.

The ARTIFACT half of the drift run. `_drift_run_findings` says what a finding
IS; this module says what filing one MEANS — the proposal document, the path
under the governed spec tree it comes to rest at, and the two readings of that
tree the pass needs before it files: which drift-origin identities are already
filed, and how many drift-origin proposals are currently OPEN.

FILING IS WRITING THE PROPOSAL DOCUMENT, and that is the decision worth
recording. The detection coverage-record contract says the pass files "through
the cross-boundary propose-change handoff", and this repository's existing
handoff — `orchestrator drift-capture` — routes each finding to a
`propose-change` CLI the CALLER injects. A reconcile pass has no such injection
and nothing to inject: the root timer fires it with no spec-side Driver in
reach. The handoff's whole OUTPUT is a `<topic>.md` under
`<spec_root>/proposed_changes/`, which is the artifact `revise` adjudicates and
the one Scenario 207 names ("the proposal rests under proposed_changes for
revise"), so the pass authors that artifact directly. ONE path, not two: a
build that routed through an injected CLI when one was configured and wrote the
file otherwise would be two authorities on one document, and the two would
drift in the direction nothing announces — both producing a well-formed
proposal.

NOTHING HERE DECIDES ANYTHING. The pass "MUST NOT accept, modify or reject any
proposal", and that holds structurally rather than carefully: the only write in
this module creates a file under `proposed_changes/`, and the only reads are of
that directory and of the archived `history/vNNN/proposed_changes/` trees. No
revision record is written, no `history/` directory is created, and no existing
document is opened for writing.

THE ALREADY-FILED SET SPANS THE ARCHIVE AS WELL AS THE OPEN QUEUE, and the two
halves are not interchangeable. An identity whose proposal has been RATIFIED is
no longer open, but it HAS been filed — and a duplicate check that read only
the open queue would re-file every finding the maintainer has already disposed
of, for ever, one proposal per ten-minute tick. The OPEN count, by contrast, is
the open queue alone, because that is what `dispatcher.drift_proposal_queue_cap`
bounds: a cap that counted ratified proposals would close permanently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._drift_run_findings import DriftFinding

__all__: list[str] = [
    "DRIFT_ORIGIN_FIELD",
    "FINDING_IDENTITY_FIELD",
    "PROPOSED_CHANGES_DIRNAME",
    "drift_proposal_document",
    "file_drift_proposal",
    "filed_finding_identities",
    "open_drift_origin_proposals",
    "target_spec_files",
]

# The two front-matter fields that make a document a DRIFT-ORIGIN proposal and
# tie it to the finding it was filed for. Both are read back by this module and
# by the needs-attention lane, so they are named here once.
DRIFT_ORIGIN_FIELD = "drift_origin"
FINDING_IDENTITY_FIELD = "finding_identity"

PROPOSED_CHANGES_DIRNAME = "proposed_changes"

_HISTORY_DIRNAME = "history"
_FRONT_MATTER_FENCE = "---"
_DRIFT_ORIGIN_VALUE = "dispatcher-drift-run"
_NO_TARGET = "(none — no existing heading would state this behaviour)"
_MOTIVATION = (
    "Filed unattended by the Dispatcher's per-merge drift run, which livespec "
    "core permits as the machine path. Acceptance is NOT the pass's to take: "
    "this proposal rests here for `revise` and its human gate, and the pass has "
    "taken no decision on it."
)


def _summary(*, finding: DriftFinding, target: str) -> str:
    """The one sentence the proposal's Summary states about the judgement."""
    return (
        f"The spec-stated judgement reports the behaviour default-branch merge "
        f"{finding.merge} adds as `{finding.kind}` against the ratified "
        f"specification. The generalization target is {target}."
    )


def _instruction(*, target: str) -> str:
    """What the proposal asks a revise pass to do with the target heading."""
    return (
        f"Generalize {target} so that it states the behaviour below, or state "
        f"that behaviour under a new heading where no existing one generalizes "
        f"to it. The behaviour, as the merge records it:"
    )


def target_spec_files(*, spec_tree: dict[str, str], finding: DriftFinding) -> tuple[str, ...]:
    """The spec files the proposal targets, resolved from the generalization target.

    A verdict's `generalization_target` is HEADING TEXT and carries no file of
    its own, so the file is found by asking which governed spec files carry that
    heading. With no target at all the proposal names NO file, which is honest:
    where a new heading belongs is a human's call, and a guess made here would
    enter the record a human adjudicates as though the judgement had made it.
    """
    if finding.generalization_target is None:
        return ()
    return tuple(
        path for path in sorted(spec_tree) if finding.generalization_target in spec_tree[path]
    )


def drift_proposal_document(
    *, finding: DriftFinding, author: str, now: str, targets: tuple[str, ...]
) -> str:
    """The proposal document ONE finding is filed as.

    Carries the drift origin and the finding identity in its front matter —
    the origin so `revise` and the queue cap can recognise a machine-filed
    proposal, the identity so a retried pass recognises its own earlier filing.
    The verdict's own rationale is quoted rather than paraphrased: it is the
    judgement's reason, and a paraphrase would put this module's words into the
    record a human adjudicates.
    """
    target = finding.generalization_target or _NO_TARGET
    return "\n".join(
        [
            _FRONT_MATTER_FENCE,
            f"topic: {finding.identity}",
            f"author: {author}",
            f"created_at: {now}",
            f"{DRIFT_ORIGIN_FIELD}: {_DRIFT_ORIGIN_VALUE}",
            f"{FINDING_IDENTITY_FIELD}: {finding.identity}",
            _FRONT_MATTER_FENCE,
            "",
            f"## Proposal: State the behaviour merge {finding.merge} adds",
            "",
            "### Target specification files",
            "",
            *(f"- {path}" for path in targets),
            "",
            "### Summary",
            "",
            _summary(finding=finding, target=target),
            "",
            "### Motivation",
            "",
            _MOTIVATION,
            "",
            f"The judgement's own rationale: {finding.rationale}",
            "",
            "### Proposed Changes",
            "",
            _instruction(target=target),
            "",
            "```text",
            finding.statement,
            "```",
            "",
        ]
    )


def filed_finding_identities(*, spec_root: Path) -> frozenset[str]:
    """Every finding identity already filed — OPEN or ARCHIVED, in that order.

    Spans the archive because a ratified proposal has been filed and must not
    be filed again; see the module docstring for what reading the open queue
    alone costs.
    """
    return frozenset(
        identity
        for document in _proposal_documents(spec_root=spec_root)
        for identity in [_front_matter_value(document=document, field=FINDING_IDENTITY_FIELD)]
        if identity is not None
    )


def open_drift_origin_proposals(*, spec_root: Path) -> tuple[Path, ...]:
    """Every OPEN drift-origin proposal, in path order — the queue the cap bounds."""
    return tuple(
        path
        for path in sorted((spec_root / PROPOSED_CHANGES_DIRNAME).glob("*.md"))
        if _front_matter_value(document=_read(path=path), field=DRIFT_ORIGIN_FIELD) is not None
    )


def file_drift_proposal(*, spec_root: Path, finding: DriftFinding, document: str) -> Path:
    """Write ONE finding's proposal into the open queue, and return its path."""
    directory = spec_root / PROPOSED_CHANGES_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{finding.identity}.md"
    _ = path.write_text(document, encoding="utf-8")
    return path


def _proposal_documents(*, spec_root: Path) -> tuple[str, ...]:
    """The text of every proposal document under the tree, open and archived."""
    open_queue = sorted((spec_root / PROPOSED_CHANGES_DIRNAME).glob("*.md"))
    archived = sorted((spec_root / _HISTORY_DIRNAME).glob(f"*/{PROPOSED_CHANGES_DIRNAME}/*.md"))
    return tuple(_read(path=path) for path in [*open_queue, *archived])


def _read(*, path: Path) -> str:
    """One document's text, or empty when it cannot be read.

    An unreadable document carries no identity this module can act on, and it
    is NOT evidence that the identity is unfiled — but the only consequence of
    answering empty is that a finding is filed twice, which `revise` can see
    and dispose of, whereas raising here would stop the whole pass over one
    file somebody left in a bad state.
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _front_matter_value(*, document: str, field: str) -> str | None:
    """One front-matter field's value, or None when the block does not carry it.

    Reads only the LEADING fenced block, so a `drift_origin:` line a proposal's
    own prose quotes — this proposal format is itself a thing proposals get
    written about — cannot make an ordinary document read as machine-filed.
    """
    lines = document.splitlines()
    if not lines or lines[0].strip() != _FRONT_MATTER_FENCE:
        return None
    prefix = f"{field}:"
    for line in lines[1:]:
        if line.strip() == _FRONT_MATTER_FENCE:
            return None
        if line.startswith(prefix):
            return line[len(prefix) :].strip() or None
    return None
