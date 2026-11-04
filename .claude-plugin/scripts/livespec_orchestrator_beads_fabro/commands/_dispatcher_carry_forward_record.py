"""The Proof of Done record, as the SANDBOX reads it, in ONE account.

`SPECIFICATION/contracts.md` section "Definition-of-Done and Proof-of-Done
stages" -> "The observation scope" (v138) makes a changed-head `pr_refresh` read
the verified record's own prose: its working-directory declaration, its numbered
reproduction steps, the single fenced text block each step gives as its captured
proof, and the `Read:` identity line of every working-tree path operand. None of
that is reachable from the host -- the decision runs INSIDE the sandbox, against
the clone's working tree and object store -- so the reader ships as a program
fragment, stdlib-only, for the reason `_dispatcher_publication_head` records: the
sandbox clone is the GOVERNED repository and carries no copy of this package.

WHY THE HEADER AND HEAD READER MOVED HERE. It was inline in
`_dispatcher_publication_head`, which was correct while that was the only
materialized program reading a record. It is not any more. A second inline copy
would be a SECOND ACCOUNT of one format, and that module measured what a second
account costs: a reasonable-looking line-two `grep` for the publish-head label
returned NOTHING on both committed real payloads. So `record_reader_fragment` is
the one text, both programs compose it, and both stay held equal to the
host-side `published_head` by that module's own equality test.

WHY THE HEADER PARSE AND THE IDENTITY TEST ARE SEPARATE READINGS. A header is
record-SHAPED once its title and verdict are the ratified ones; whether its
third field carries a readable publishing identity is a different question, and
a reader that answered only "record / not a record" could not tell a comment
that is not a record from one that is not a header at all. The cost of
collapsing them is measured: a capture that expanded an unset `$FABRO_RUN_ID`
into `printf '... run %s ...'` posted the bare introducer, the reader correctly
dropped the comment, and the publication-head program then reported pull request
2712 of `livespec-dev-tooling` as carrying no captured record -- naming the one
stage that had demonstrably run, while the comment an operator had to read went
unnamed (`bd-ib-oa67lv`, run 01M5E8H65Z04).

WHY A STEP'S COMMAND IS ITS INLINE CODE SPAN. The clause says each step "MUST
carry exactly one command", and both capture prompts write every command as a
Markdown code span -- `` `git rev-parse HEAD` `` -- because the record is prose a
human reads. So the mechanical reading of "the step's command" is its code
spans: exactly one is the command, none means the step carries no command, and
two or more means it carries more than one. Those are the three answers the
clause distinguishes, and the grammar fragment already spells the latter two.

WHY A STEP'S CAPTURED PROOF IS THE FENCED BLOCK BETWEEN IT AND WHAT ENDS IT. The
clause requires the captured proof to be "the single fenced text block the
verified record gives for that step", and a record is a flat document: the only
mechanical way to say which block belongs to which step is POSITION. A block
after step N and before step N+1, the next heading, or the end of the body is
step N's. A step with no block, and a step with two, both make the decision
`reproof_required` naming that step -- which is the Scenario 178 outline with its
`0` and `2` examples, and it is deliberately the fail-closed direction: a record
whose proof cannot be attributed to a step has not said what to replay.

WHY THE WORKING-DIRECTORY READING IS TRI-STATE. `None` means the record declared
no working directory at all; a string means it declared that one. The clause
gives "no line" and "some other directory" the SAME answer -- every step outside
the grammar -- but not the same RECORD: only the second can name the directory
the record stated, and a reader collapsing them could not write that finding.
The grammar module owns both spellings so the prompt that WRITES the line and
the decision that READS it cannot drift.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_grammar import (
    READ_IDENTITY_LABEL,
    WORKING_DIRECTORY_PREFIX,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    FACTORY_RECORD_VERDICTS,
    PUBLISH_HEAD_LABEL,
)

__all__: list[str] = [
    "record_parse_fragment",
    "record_reader_fragment",
]

# The header, verdict and publish-head reader, verbatim as it stood inline in
# `_dispatcher_publication_head`. Its four decisions are unchanged and each is
# load-bearing: a FENCED line is skipped (a replay legitimately `cat`s an earlier
# record, and matching inside the fence would attribute that record's head to
# this one); the comparison is casefolded and backticks are stripped; only a FULL
# forty-character sha counts; and a record naming TWO different heads answers
# "none", because a record that cannot say which tree it proved has not proved
# one.
_READER_FRAGMENT = '''
import re

LABEL = "__LABEL__"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
HEADER_SEPARATOR = "\\u2014"
IDENTITY_PREFIXES = ("run ", "session ", "human ")
VERDICTS = __VERDICTS__


def fence_after(fence, delimiter):
    """The open fence after one delimiter line, or None outside a fence."""
    if fence is None:
        return delimiter
    if delimiter[0] == fence[0] and len(delimiter) >= len(fence):
        return None
    return fence


def declared_sha(line):
    stripped = line.strip()
    prefix = LABEL + ":"
    if not stripped.casefold().startswith(prefix.casefold()):
        return None
    value = stripped[len(prefix):].strip().strip("`").casefold()
    return value if FULL_SHA.match(value) is not None else None


def published_head(body):
    """The full sha one record's PROSE declares, or None when it declares none."""
    found = set()
    fence = None
    for line in body.splitlines():
        delimiter = FENCE.match(line)
        if delimiter is not None:
            fence = fence_after(fence, delimiter.group(1))
            continue
        if fence is not None:
            continue
        sha = declared_sha(line)
        if sha is not None:
            found.add(sha)
    return found.pop() if len(found) == 1 else None


def header_fields(body):
    """One comment's record-header fields, or None when it is not header-shaped.

    The SHARED parse the three readings below sit on. A header is "shaped" once
    its title and verdict are the ratified ones; whether its PUBLISHING IDENTITY
    is readable is a separate question, and keeping the two apart is what lets a
    refusal say which half of the header failed.
    """
    lines = body.splitlines()
    if not lines:
        return None
    fields = [part.strip() for part in lines[0].split(HEADER_SEPARATOR)]
    if len(fields) < 3 or fields[0] != "Proof of Done" or fields[1] not in VERDICTS:
        return None
    return fields


def header_verdict(body):
    """The verdict a record-SHAPED header names, whatever identity it carries.

    WIDER than `record_verdict` on purpose, and the width is the whole point: a
    header whose identity field carries no run id is not a record, so
    `record_verdict` drops the comment -- and a reader that only ever saw records
    reported that drop as a pull request carrying no record of that verdict at
    all, which names a stage that had demonstrably run.
    """
    fields = header_fields(body)
    return None if fields is None else fields[1]


def header_identity_field(body):
    """The PUBLISHING IDENTITY field of a record-shaped header, else None.

    Returned RAW, because a refusal about it has to quote what the header
    actually says: `run` with nothing after it and `run-1` with no introducer at
    all are two ways to carry no run id, and an operator reading the diagnostic
    needs to see which one was published.
    """
    fields = header_fields(body)
    return None if fields is None else fields[2]


def record_verdict(body):
    """The verdict one canonical factory-record header declares, else None."""
    fields = header_fields(body)
    if fields is None:
        return None
    if not any(fields[2].startswith(prefix) for prefix in IDENTITY_PREFIXES):
        return None
    return fields[1]
'''

# The reproduction-step parse the carry-forward decision adds on top of that
# reader. A RAW outer string, so every backslash below is the one the inner
# source needs.
_PARSE_FRAGMENT = r'''
STEP_START = re.compile(r"^\s*([0-9]+)\.\s+(.*)$")
HEADING = re.compile(r"^ {0,3}#{1,6}\s")
CODE_SPAN = re.compile(r"`([^`]+)`")
WORKING_DIRECTORY_PREFIX = "__WORKING_DIRECTORY_PREFIX__"
READ_IDENTITY_LABEL = "__READ_IDENTITY_LABEL__"


def prose_lines(body):
    """Every line of one record that is PROSE, i.e. outside every fenced block.

    Shared by the three prose readings below, because "outside a fence" is the
    one property all three depend on and a per-reader fence walk is how one of
    them comes to read a proof's own output as a declaration.
    """
    kept = []
    fence = None
    for line in body.splitlines():
        delimiter = FENCE.match(line)
        if delimiter is not None:
            fence = fence_after(fence, delimiter.group(1))
            continue
        if fence is None:
            kept.append(line)
    return kept


def declared_working_directory(body):
    """The working directory one record's PROSE declares, or None for none.

    Tri-state on purpose: see the module docstring. A record declaring the line
    twice answers the FIRST, because the decision measures it against the root
    form and re-proves either way -- while a reader answering None there would
    report "declared nothing" about a record that declared two things.
    """
    for line in prose_lines(body):
        stripped = line.strip()
        if stripped.startswith(WORKING_DIRECTORY_PREFIX):
            return stripped[len(WORKING_DIRECTORY_PREFIX):].strip()
    return None


def read_identities(body):
    """Every `Read: <path> <identity>` the PROSE declares, canonical path to identity.

    A path declared twice with DIFFERENT identities maps to None, which the
    decision reports as a missing read identity for that path: a record that
    cannot say which bytes it read of one file has not recorded a read of it.
    """
    found = {}
    prefix = READ_IDENTITY_LABEL + ":"
    for line in prose_lines(body):
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        fields = stripped[len(prefix):].split()
        if len(fields) != 2:
            continue
        path = canonical_path(fields[0])
        if path is None:
            continue
        identity = fields[1].strip("`").casefold()
        if path in found and found[path] != identity:
            found[path] = None
        else:
            found.setdefault(path, identity)
    return found


def reproduction_steps(body):
    """Every numbered reproduction step, in record order, with its fenced blocks.

    ONE pass, because the two readings are positional and interleaved: a step's
    proofs are the blocks between it and whatever ends it, so a second pass over
    the same lines would have to re-derive the boundaries the first already
    found.
    """
    steps = []
    open_step = None
    fence = None
    block = None
    for line in body.splitlines():
        delimiter = FENCE.match(line)
        if delimiter is not None:
            fence = fence_after(fence, delimiter.group(1))
            if fence is not None:
                block = []
            else:
                if open_step is not None and block is not None:
                    open_step["proofs"].append("\n".join(block))
                block = None
            continue
        if fence is not None:
            if block is not None:
                block.append(line)
            continue
        start = STEP_START.match(line)
        if start is not None:
            open_step = {"number": start.group(1), "text": start.group(2), "proofs": []}
            steps.append(open_step)
            continue
        if HEADING.match(line) is not None:
            open_step = None
            continue
        if open_step is not None:
            open_step["text"] = open_step["text"] + "\n" + line
    return steps


def step_command(step):
    """The ONE command a step carries, or the reason it carries no single command."""
    spans = CODE_SPAN.findall(step["text"])
    if not spans:
        return None, NO_COMMAND
    if len(spans) > 1:
        return None, TWO_COMMANDS
    return spans[0], None
'''


def record_reader_fragment() -> str:
    """The record header and publish-head reader, with its constants substituted.

    A function rather than a constant for the reason `proof_head_program_source`
    gives: a reader must be able to SEE that the label came from
    `PUBLISH_HEAD_LABEL` and the verdict set from `FACTORY_RECORD_VERDICTS`, not
    from literals typed twice.
    """
    return _READER_FRAGMENT.replace("__LABEL__", PUBLISH_HEAD_LABEL).replace(
        "__VERDICTS__", repr(FACTORY_RECORD_VERDICTS)
    )


def record_parse_fragment() -> str:
    """The reproduction-step parse, with the two record-line spellings substituted.

    It composes ONTO `record_reader_fragment` and the grammar fragment rather
    than standing alone: it reuses `FENCE`, `fence_after` and `canonical_path`,
    and each spelling comes from the module that owns it.
    """
    return _PARSE_FRAGMENT.replace(
        "__WORKING_DIRECTORY_PREFIX__", WORKING_DIRECTORY_PREFIX
    ).replace("__READ_IDENTITY_LABEL__", READ_IDENTITY_LABEL)
