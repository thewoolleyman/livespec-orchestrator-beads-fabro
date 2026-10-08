"""The ONE primitive that renders a proof record, so that no session formats one.

The host-leg clause of `SPECIFICATION/contracts.md` (v115) requires that "the
implementation MUST provide one posting primitive that renders these records, so
that no session hand-formats one", and the plan-record clause requires the same of
plan records. This module is the render half both of those primitives reach for.

WHY THE TITLE IS A PARAMETER. The two records differ in their first line — `Proof
of Done` for an item, `Plan Proof of Done` for a plan — and in where they are
posted: the item's pull request, the plan's epic. They do NOT differ in body
structure, and a second renderer for the plan half would be a second place for the
two placement rules below to be got wrong.

THIS RENDERER WRITES THE SHAPE THE `proof_verify` PROMPT ALREADY PRESCRIBES, and
that is a requirement rather than a courtesy. `_dispatcher_proof_record` is the one
reader of every published record, factory and host alike, and it was built against
the prompt's worked shape. A renderer that published a DIFFERENT well-formed shape
would be read by that reader as a record whose assertions are all unevidenced — so
the records a machine publishes and the records an agent hand-writes have to look
the same to it.

TRAP 1 — THE REPRODUCTION VERDICT IS A PLAIN LINE, NEVER A BULLET. The reader finds
the verdict by taking a line, stripping it, case-folding it, and asking whether it
STARTS WITH `reproduced:`. A bullet — `- Reproduced: yes.` — starts with the list
marker, so it never matches, and the reader answers `None`: the UNEVIDENCED answer,
which parks a perfectly good verified item on NEEDS_ATTENTION. Measured 2026-10-04
while building this module: the bullet form rendered, parsed as a record, carried
the right verdict and identity, and reported every assertion unevidenced. Nothing
about that output says the line was in the wrong form.

TRAP 2 — AN ASSERTION'S SECTION CARRIES NO SUB-HEADINGS. The reader splits a body
into per-assertion sections at its prose headings, so a `### Reproduction steps`
heading inside an assertion opens a NEW section and everything after it — the
proof, and the reproduction verdict with it — lands outside the section carrying
the assertion text. The labels are therefore plain lines, exactly as the prompt
writes them, and the whole assertion stays in one section.

WHY THE PROOF FENCE IS SIZED TO ITS CONTENT. The clause requires "a fenced code
block for each text capture", and a capture routinely prints a Markdown file, a
spec excerpt, or another record — output carrying its own triple-backtick fences.
A fixed three-backtick wrapper is CLOSED by the first of those, after which the
rest of the proof is prose to the reader: its `#` lines open new sections, and the
assertion's verdict is read from whichever one it lands in. CommonMark closes a
fence only on a run at least as long as the opener, so the wrapper is one backtick
longer than the longest run the proof contains.

WHAT SHARING THIS RENDERER DOES NOT GIVE THE PLAN SLICE, recorded so the gap is
not read as an oversight. `_dispatcher_proof_record` reads records on an ITEM's
pull request and its header match is scoped to that title, so it reports a `Plan
Proof of Done` first line as prose and returns no record for it. That is the right
answer here — a plan record on an item's pull request is not that item's evidence —
and it means the plan slice owes a reader of its own, or a title parameter on that
one, rather than inheriting this module and assuming the round trip comes with it.

WHY `governing_scenario` IS OPTIONAL AND WHO OWNS THE EITHER/OR. The item record's
clause requires "the governing scenario ... or the statement that no scenario
governs it", and the PLAN record's clause requires no such field at all. `None`
therefore means "render no claim about scenarios", which is the plan arm; the
item-side caller discharges its either/or by passing the scenario or the
`NO_GOVERNING_SCENARIO` statement explicitly. Defaulting `None` to the statement
would make a plan record assert something its clause never asked for, and nothing
downstream would notice.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attachment import (
    ProofAttachment,
)

__all__: list[str] = [
    "ASSERTION_HEADING_PREFIX",
    "GOVERNING_SCENARIO_LABEL",
    "NO_GOVERNING_SCENARIO",
    "PROOF_HEADING",
    "PROOF_MODE_LABEL",
    "REPRODUCED_LABEL",
    "REPRODUCTION_STEPS_HEADING",
    "RecordAssertion",
    "render_proof_record",
]

ASSERTION_HEADING_PREFIX = "Assertion"
GOVERNING_SCENARIO_LABEL = "Governing scenario"
NO_GOVERNING_SCENARIO = "no scenario governs this assertion"
PROOF_MODE_LABEL = "Proof mode"
REPRODUCED_LABEL = "Reproduced"
REPRODUCTION_STEPS_HEADING = "Reproduction steps"
PROOF_HEADING = "Proof"

# The ratified header separator, which the reader splits the first line on.
_HEADER_SEPARATOR = "—"
_REPRODUCED_YES = "yes"
_REPRODUCED_NO = "no"
_BACKTICK_RUN = re.compile(r"`+")
_MINIMUM_FENCE = 3


@dataclass(frozen=True, kw_only=True)
class RecordAssertion:
    """One assertion's section of a proof record.

    `reproduced` is tri-state for the same reason the reader's answer is: `None`
    means this record makes NO claim about reproduction, which is the honest shape
    of a capture — a `host_recorded` or `captured` record is the FIRST leg and has
    nothing yet to have reproduced. Rendering `no` for it would publish a failing
    verdict against the capture's own assertions.
    """

    text: str
    proof_mode: str
    governing_scenario: str | None
    steps: tuple[str, ...]
    proof: str
    reproduced: bool | None
    # Set when this proof was too large to publish inline and travels as an asset
    # instead (`_dispatcher_proof_attachment`). `None` — the default, and the
    # ordinary case — renders the fenced inline proof exactly as it always has.
    #
    # `proof` is deliberately NOT cleared when an attachment is set: it is the
    # bytes the digest was taken over, so the budget measurement and the upload
    # both still have the subject in hand, and the renderer decides which of the
    # two forms the record carries. A field that replaced the proof would make the
    # record the only remaining account of what was attached.
    attachment: ProofAttachment | None = None

    def render(self, *, index: int) -> str:
        """This assertion's whole section, with no trailing newline.

        `index` is one-based and comes from the caller's enumeration rather than
        from anything on this value, because the clause orders the sections by
        Definition of Done position and an assertion does not know its own.

        The verdict is written LAST, after the proof, which is where the prompt's
        worked shape puts it: a reader of the comment sees what was run and what it
        produced before being told whether it reproduced.
        """
        lines = [f"## {ASSERTION_HEADING_PREFIX} {index} — {self.text}", ""]
        lines.extend([f"{PROOF_MODE_LABEL}: {self.proof_mode}", ""])
        if self.governing_scenario is not None:
            lines.extend([f"{GOVERNING_SCENARIO_LABEL}: {self.governing_scenario}", ""])
        lines.extend([f"{REPRODUCTION_STEPS_HEADING}:", ""])
        lines.extend(f"{number}. {step}" for number, step in enumerate(self.steps, start=1))
        lines.extend(["", f"{PROOF_HEADING}:", ""])
        lines.extend(self._proof_lines())
        if self.reproduced is not None:
            verdict = _REPRODUCED_YES if self.reproduced else _REPRODUCED_NO
            lines.extend(["", f"{REPRODUCED_LABEL}: {verdict}."])
        return "\n".join(lines)

    def _proof_lines(self) -> list[str]:
        """The proof itself, inline in a sized fence, or the attachment reference.

        The inline arm is byte-for-byte what this renderer has always produced, and
        is asserted so by the golden-master fixture: the attachment path is additive,
        so a record that was publishable before must render identically now.

        The attachment arm is deliberately NOT fenced. The record reader ignores
        fenced content — it cannot otherwise tell a verdict a verifier authored from
        one a proof printed — so a reference inside a fence would be invisible to the
        very surfaces that must check its digest.
        """
        if self.attachment is not None:
            return self.attachment.render().splitlines()
        fence = _fence_for(text=self.proof)
        return [fence, self.proof.rstrip("\n"), fence]


def render_proof_record(
    *,
    title: str,
    verdict: str,
    identity: str,
    timestamp: str,
    build: BuildIdentity,
    assertions: Sequence[RecordAssertion],
) -> str:
    """One whole record comment body, ready to post.

    `identity` arrives already carrying its `session ` / `human ` introducer,
    because the reader treats an introducer-less third field as a NON-record and
    the kind of identity follows from who computed it rather than from anything
    visible here.
    """
    header = f"{title} {_HEADER_SEPARATOR} {verdict} {_HEADER_SEPARATOR} {identity}"
    sections = [f"{header} {_HEADER_SEPARATOR} {timestamp}", build.render()]
    sections.extend(one.render(index=index) for index, one in enumerate(assertions, start=1))
    return "\n\n".join(sections) + "\n"


def _fence_for(*, text: str) -> str:
    """A backtick fence at least one longer than the longest run `text` contains."""
    longest = max((len(run.group()) for run in _BACKTICK_RUN.finditer(text)), default=0)
    return "`" * max(_MINIMUM_FENCE, longest + 1)
