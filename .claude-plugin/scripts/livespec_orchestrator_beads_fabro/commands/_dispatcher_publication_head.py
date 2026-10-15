"""The head whose proof was captured AND verified, established inside the sandbox.

WHAT THIS EXISTS FOR. `SPECIFICATION/contracts.md` section
"Definition-of-Done and Proof-of-Done stages" -> "Scripted publication and
proof-head integrity" requires the `pr` command stage to "verify its current
head against the head whose proof was verified", and says in as many words that
"a later head change requires fresh proof; publication MUST NOT reuse a verified
record from before that change". The head a run PUSHED is not that head: a
pushed-head marker says what this run put on the branch, not what any record
proved, and the two diverge in exactly the case the clause is about.

WHY A MATERIALIZED PROGRAM RATHER THAN SHELL IN THE NODE. Establishing the head
means READING THE PROOF OF DONE RECORD FORMAT, and this repository already has
ONE reader of it -- `_dispatcher_resume_anchor.published_head`, which is
fence-aware, case-insensitive, strips backticks, requires a full sha and
answers `None` when a record names two. A second reader hand-rolled in the
node's `script` would be a second account of one format, and the cost is
measured rather than hypothetical: a line-two `grep` for the label, written
against the prompt's own wording, returns NOTHING on both committed real
payloads (`tests/integration/fixtures/proof_records/`), because neither record
carries the label on that line at all. That reader would have reported every
real record as headless while looking perfectly reasonable.

So the reader is Python, it lives here, and the Dispatcher MATERIALIZES it into
the sandbox the way `_dispatcher_plugin_cache_gate` already materializes its
gate: the program lands below the plugins root at prepare time and the node
re-enters it by the path the overlay names. The program is STDLIB-ONLY and
carries no livespec import, for the reason that gate records -- the sandbox
clone is the GOVERNED repository and has no copy of this package.

THE TWO IMPLEMENTATIONS ARE HELD EQUAL BY TEST, NOT BY HOPE.
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_publication_head.py`
runs the materialized program's own reader beside `published_head` over the
committed real payloads and over synthetic headed, fenced, duplicate-naming and
malformed records, and requires the same answer from both. That binding is what
makes "one format" true; the label and the verdict names are substituted in from
their owning constants so there is also only one SPELLING.

WHY IT REQUIRES BOTH VERDICTS. The caller asks for `captured` and `verified`
together, and the conjunction is the point: a verified record alone can post-date
a capture of a different tree, and a captured record alone was never replayed.
Both must name the same head, and the stage then requires that head to equal the
pull request's own -- three values, two comparisons, and no step where a pushed
marker stands in for a proof.

AND THE VERIFIED RECORD MUST BE THE NEWEST FACTORY RECORD ON THE PULL REQUEST,
which is the sharpest form of the clause rather than a second rule. Only
`proof_verify` precedes publication, so in any conforming run the newest factory
record IS the verification; anything newer -- a `not_reproduced` the replay
posted afterwards, a `not_captured`, or a fresh `captured` a changed-head
refresh earned with no replay yet behind it -- means the verification no longer
describes the tree about to be published. Stating it as "nothing is newer"
rather than as a list of forbidden successors is what keeps a verdict added
later from quietly falling outside the test, and it is why an older record that
happens to share the verified SHA cannot rescue the chain: the comparison is by
POSITION, never by sha.

EVERY ARM FAILS CLOSED, and each says which measurement stopped it, because
"the records do not agree", "a newer record supersedes the verification" and
"the records could not be read" have three different remedies and a shared exit
would make them one finding.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_record import (
    record_reader_fragment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_CARRIED_FORWARD,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "PROOF_HEAD_ANCHOR_VERDICTS",
    "PROOF_HEAD_PROGRAM_FILENAME",
    "PROOF_HEAD_REQUIRED_VERDICTS",
    "proof_head_program_path_expansion",
    "proof_head_program_prepare_steps_block",
    "proof_head_program_source",
]

# The program's filename below the sandbox plugins root.
#
# Fail-closed is the node's own existence check rather than a `${VAR:?}` guard:
# a sandbox the prepare step did not reach carries no program, and publishing on
# an unchecked proof identity is the one outcome that must not be reachable.
PROOF_HEAD_PROGRAM_FILENAME = "livespec-publication-head.py"

# Both verdicts the `pr` stage requires, in the order it names them. Read off the
# record module's own constants so the program cannot come to spell a verdict the
# records do not carry.
PROOF_HEAD_REQUIRED_VERDICTS: tuple[str, ...] = (VERDICT_CAPTURED, VERDICT_VERIFIED)

# The two verdicts a record may NAME the publishable head with, newest first in
# precedence. The v138 clause moved the `pr` stage's comparison onto "the head
# named by the latest record of this run that is either `verified` or
# `carried_forward`", which is a different question from the one
# `PROOF_HEAD_REQUIRED_VERDICTS` answers and the two must not be collapsed.
#
# WHY A CARRY-FORWARD SUPERSEDES THE CAPTURE/REPLAY AGREEMENT RATHER THAN
# JOINING IT. The capture and the replay each name the head THEY ran on, and on
# a carried-forward publication no stage ever ran on the head being published --
# that is the entire saving. So requiring all three to agree would refuse every
# carried-forward publication, and refuse it with a head-mismatch diagnostic
# that reads exactly like a genuine stale proof. The agreement is still required
# when the anchor IS the verified record, which is every ordinary run.
PROOF_HEAD_ANCHOR_VERDICTS: tuple[str, ...] = (VERDICT_VERIFIED, VERDICT_CARRIED_FORWARD)

# The imports the composed program needs, hoisted so the shared record reader
# carries only its own `re`. A record-reading program needs the forge
# (`subprocess`), its payload (`json`) and its own exit (`sys`); the reader
# fragment needs none of the three.
_PROGRAM_PREAMBLE = """
import json
import subprocess
import sys
"""

# The program's OWN half: the anchor set, the forge read, and the ladder from a
# comment list to one publishable head.
#
# THE RECORD READER IT SITS ON TOP OF IS NO LONGER INLINE HERE. It is
# `_dispatcher_carry_forward_record.record_reader_fragment`, which is where the
# `__LABEL__` and `__VERDICTS__` substitutions now happen and where the four
# decisions this comment used to describe are documented. The move is what keeps
# this module's own warning TRUE once a SECOND materialized program reads the
# same format: the carry-forward decision program composes the identical text,
# so there is still ONE account of the header parse and the publish-head
# reading rather than two. The equality binding is unchanged -- the composed
# result is still run beside the host-side `published_head` over the same
# bodies, which is what makes "one format" a measured claim.
_PROGRAM_SOURCE = '''
ANCHOR_VERDICTS = __ANCHOR_VERDICTS__


def fail(message):
    sys.stderr.write("livespec publication-head: " + message + "\\n")
    raise SystemExit(1)


def comment_bodies(number):
    result = subprocess.run(
        ["gh", "pr", "view", number, "--json", "comments"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        fail("the forge could not be asked for the comments on pull request #"
             + number + "; " + result.stderr.strip())
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        fail("the forge's comment payload for pull request #" + number
             + " did not parse as JSON, so no record could be read")
    comments = payload.get("comments")
    if not isinstance(comments, list):
        fail("the forge's comment payload for pull request #" + number
             + " carries no comments array, so no record could be read")
    return [one.get("body") or "" for one in comments if isinstance(one, dict)]


def required_verdicts(argv):
    """Every `--require <verdict>` pair, in the order the caller named them."""
    return [argv[index + 1] for index, token in enumerate(argv[2:], start=2)
            if token == "--require" and index + 1 < len(argv)]


def factory_records(bodies):
    """Each factory record as (position, verdict, declared head), in order."""
    records = []
    for index, body in enumerate(bodies):
        verdict = record_verdict(body)
        if verdict is not None:
            records.append((index, verdict, published_head(body)))
    return records


def agreed_head(number, records, required):
    """The one head every required verdict's LATEST record names."""
    latest = {}
    for index, verdict, head in records:
        latest[verdict] = (index, head)
    heads = set()
    for verdict in required:
        if verdict not in latest:
            fail("pull request #" + number + " carries no " + verdict
                 + " Proof of Done record, so there is no " + verdict
                 + " proof identity to publish against")
        if latest[verdict][1] is None:
            fail("the latest " + verdict + " Proof of Done record on pull request #"
                 + number + " names no single full publish-branch head, so the tree"
                 + " it proved cannot be established")
        heads.add(latest[verdict][1])
    if len(heads) != 1:
        fail("the required records on pull request #" + number
             + " name different publish-branch heads ("
             + ", ".join(sorted(heads)) + "), so no one tree carries both"
             + " a capture and a replay")
    return heads.pop()


def anchoring_record(number, records):
    """The LATEST record that may name the head publication readies.

    Read by POSITION across both anchor verdicts rather than per-verdict,
    because a `carried_forward` record SUPERSEDES the verified record it
    carries: on a chain of carry-forwards an older verified record still
    exists, still names a head, and must not win.
    """
    anchors = [one for one in records if one[1] in ANCHOR_VERDICTS]
    if not anchors:
        fail("pull request #" + number + " carries no verified or carried_forward"
             + " Proof of Done record, so no record names a head this stage may"
             + " publish against")
    index, verdict, head = anchors[-1]
    if head is None:
        fail("the latest " + verdict + " Proof of Done record on pull request #"
             + number + " names no single full publish-branch head, so the tree"
             + " it proved cannot be established")
    return index, verdict, head


def refuse_superseded_anchor(number, records, anchor_index):
    """Refuse when ANY factory record is newer than the anchoring record."""
    newer = [(index, verdict) for index, verdict, _ in records if index > anchor_index]
    if not newer:
        return
    index, verdict = newer[-1]
    fail("pull request #" + number + " carries a newer " + verdict
         + " Proof of Done record at position " + str(index) + ", after the"
         + " anchoring record at position " + str(anchor_index) + ", so that"
         + " proof no longer describes the tree about to be published;"
         + " a fresh capture and replay are owed")


def main(argv):
    """Establish the head to publish against, or fail closed naming the measurement.

    The REQUIRED agreement is graded first and the ANCHOR second, and the order
    is load-bearing rather than tidy: a pull request carrying no records at all
    must report the missing capture, which is the first thing a run publishes
    and the first thing an operator would look for, rather than reporting an
    absent carry-forward decision that nothing in an ordinary run ever writes.
    """
    if len(argv) < 2 or argv[0] != "--pull-request":
        fail("usage: --pull-request <number> [--require <verdict> ...]")
    number = argv[1]
    required = required_verdicts(argv)
    if not required:
        fail("no --require <verdict> was named, so nothing would be established")
    records = factory_records(comment_bodies(number))
    agreed_head(number, records, required)
    anchor_index, _, head = anchoring_record(number, records)
    refuse_superseded_anchor(number, records, anchor_index)
    sys.stdout.write(head + "\\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def proof_head_program_source() -> str:
    """The materialized program's exact bytes: the preamble, the shared reader, this.

    A function rather than a module constant because the COMPOSITION is the
    whole guarantee: a reader comparing this against `published_head` must be
    able to see that the header parse and the publish-head reading came from the
    one shared `record_reader_fragment` -- which substitutes the LABEL from
    `PUBLISH_HEAD_LABEL` and the verdict set from `FACTORY_RECORD_VERDICTS` --
    rather than from a copy typed here a second time.
    """
    return (
        _PROGRAM_PREAMBLE
        + record_reader_fragment()
        + _PROGRAM_SOURCE.replace("__ANCHOR_VERDICTS__", repr(PROOF_HEAD_ANCHOR_VERDICTS))
    )


def proof_head_program_path_expansion() -> str:
    """The shell expansion the `pr` node resolves the program through.

    PUBLIC and spelled once, for the reason the plugin-cache gate's own root
    expansion records: a node resolving a DIFFERENT root than the prepare pass
    would find no program at all, and the failure would then read as a
    Dispatcher that never materialized one.
    """
    return f"{sandbox_plugins_root_expansion()}/{PROOF_HEAD_PROGRAM_FILENAME}"


def proof_head_program_prepare_steps_block() -> str:
    """The prepare step that lands the program below the sandbox plugins root.

    Written through a heredoc with a QUOTED delimiter, so the shell expands
    nothing inside the program: the reader carries dollar-bearing,
    shell-looking text of its own, and an unquoted heredoc would substitute
    into it.
    """
    root = sandbox_plugins_root_expansion()
    script = (
        f'set -eu\nmkdir -p "{root}"\n'
        f'cat > "{root}/{PROOF_HEAD_PROGRAM_FILENAME}" '
        f"<<'LIVESPEC_PUBLICATION_HEAD_PROGRAM'\n"
        f"{proof_head_program_source()}"
        "LIVESPEC_PUBLICATION_HEAD_PROGRAM"
    )
    return (
        "\n# --- Dispatcher-materialized publication-head program: the ONE reader of\n"
        "# --- the Proof of Done record format the scripted pr stage may use ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )
