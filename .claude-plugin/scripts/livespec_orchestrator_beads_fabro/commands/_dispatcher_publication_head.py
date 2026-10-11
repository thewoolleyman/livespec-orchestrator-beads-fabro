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
payloads (`tests/integration/fixtures/proof_records/`, PR 2538 and PR 2561),
because neither record carries the label at all. That reader would have reported
every real record as headless while looking perfectly reasonable.

So the reader is Python, it lives here, and the Dispatcher MATERIALIZES it into
the sandbox the way `_dispatcher_plugin_cache_gate` already materializes its
gate: the program lands below the plugins root at prepare time and the node
re-enters it by the path the overlay names. The program is STDLIB-ONLY and
carries no livespec import, for the reason that gate records -- the sandbox
clone is the GOVERNED repository and has no copy of this package.

THE TWO IMPLEMENTATIONS ARE HELD EQUAL BY TEST, NOT BY HOPE.
`tests/.../test_dispatcher_publication_head.py` runs the materialized program's
own reader beside `published_head` over the two committed real payloads and over
synthetic headed, fenced, duplicate-naming and malformed records, and requires
the same answer from both. That binding is what makes "one format" true; the
label and the verdict names are substituted in from their owning constants so
there is also only one SPELLING.

WHY IT REQUIRES BOTH VERDICTS. The caller asks for `captured` and `verified`
together, and the conjunction is the point: a verified record alone can post-date
a capture of a different tree, and a captured record alone was never replayed.
Both must name the same head, and the stage then requires that head to equal the
pull request's own -- three values, two comparisons, and no step where a pushed
marker stands in for a proof.

EVERY ARM FAILS CLOSED, and each says which measurement stopped it, because
"the records do not agree" and "the records could not be read" have different
remedies and a shared exit would make them one finding.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    FACTORY_RECORD_VERDICTS,
    PUBLISH_HEAD_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "PROOF_HEAD_PROGRAM_FILENAME",
    "PROOF_HEAD_REQUIRED_VERDICTS",
    "proof_head_program_path_expansion",
    "proof_head_program_prepare_steps_block",
    "proof_head_program_source",
]

# The program's filename below the sandbox plugins root.
#
# THE NODE RESOLVES THE ROOT BY SHELL EXPANSION, NOT FROM A PROJECTED PATH, and
# that is the established mechanism rather than a shortcut. The root is not known
# host-side -- it is the sandbox's own `$HOME` unless the image overrides it --
# and the pinned engine does not expand `${...}` inside an
# `[environments.*.env]` value, so a projected path would reach the node as the
# literal dollar-brace string. `_dispatcher_plugin_cache_gate` resolves its own
# program through the same expansion, which is what keeps BOTH materialized
# programs under ONE root.
#
# Fail-closed is then the node's own existence check rather than a `${VAR:?}`
# guard: a sandbox the prepare step did not reach carries no program, and
# publishing on an unchecked proof identity is the one outcome that must not be
# reachable from here.
PROOF_HEAD_PROGRAM_FILENAME = "livespec-publication-head.py"

# Both verdicts the `pr` stage requires, in the order it names them. Read off the
# record module's own constants so the program cannot come to spell a verdict the
# records do not carry.
PROOF_HEAD_REQUIRED_VERDICTS: tuple[str, ...] = (VERDICT_CAPTURED, VERDICT_VERIFIED)

# The materialized program. `__LABEL__` is substituted from `PUBLISH_HEAD_LABEL`
# so the reader and the two capture prompts name ONE line.
#
# The reader is a transcription of `published_head` plus the header parse, and it
# keeps that function's four decisions verbatim: a fenced line is skipped (a
# replay legitimately `cat`s an earlier record, and matching inside the fence
# would attribute that record's head to this one); the comparison is casefolded
# and backticks are stripped; only a FULL forty-character sha counts; and a
# record naming TWO different heads answers "none", because a record that cannot
# say which tree it proved has not proved one.
_PROGRAM_SOURCE = '''
import json
import re
import subprocess
import sys

LABEL = "__LABEL__"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
FENCE = re.compile(r"^\\s*(`{3,}|~{3,})")
HEADER_SEPARATOR = "—"
IDENTITY_PREFIXES = ("run ", "session ", "human ")
VERDICTS = __VERDICTS__


def fail(message):
    sys.stderr.write("livespec publication-head: " + message + "\\n")
    raise SystemExit(1)


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


def record_verdict(body):
    """The verdict one canonical factory-record header declares, else None."""
    lines = body.splitlines()
    if not lines:
        return None
    fields = [part.strip() for part in lines[0].split(HEADER_SEPARATOR)]
    if len(fields) < 3 or fields[0] != "Proof of Done" or fields[1] not in VERDICTS:
        return None
    if not any(fields[2].startswith(prefix) for prefix in IDENTITY_PREFIXES):
        return None
    return fields[1]


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


def main(argv):
    if len(argv) < 2 or argv[0] != "--pull-request":
        fail("usage: --pull-request <number> [--require <verdict> ...]")
    number = argv[1]
    required = [argv[index + 1] for index, token in enumerate(argv[2:], start=2)
                if token == "--require" and index + 1 < len(argv)]
    if not required:
        fail("no --require <verdict> was named, so nothing would be established")
    bodies = comment_bodies(number)
    records = []
    for index, body in enumerate(bodies):
        verdict = record_verdict(body)
        if verdict is not None:
            records.append((index, verdict, published_head(body)))
    latest = {}
    for index, verdict, head in records:
        latest[verdict] = (index, head)
    agreed = set()
    for verdict in required:
        if verdict not in latest:
            fail("pull request #" + number + " carries no " + verdict
                 + " Proof of Done record, so there is no " + verdict
                 + " proof identity to publish against")
        if latest[verdict][1] is None:
            fail("the latest " + verdict + " Proof of Done record on pull request #"
                 + number + " names no single full publish-branch head, so the tree"
                 + " it proved cannot be established")
        agreed.add(latest[verdict][1])
    if "captured" in required and "verified" in required:
        captured_index = latest["captured"][0]
        verified_index = latest["verified"][0]
        newer_failures = [verdict for index, verdict, _ in records
                          if index > verified_index and verdict in
                          ("not_captured", "not_reproduced")]
        if newer_failures:
            fail("pull request #" + number + " carries a newer "
                 + newer_failures[-1] + " Proof of Done record after its latest"
                 + " verified record, so the older verification cannot authorize"
                 + " publication")
        if captured_index > verified_index:
            fail("pull request #" + number + " carries a newer captured Proof of Done"
                 + " record with no subsequent verified replay, so the older"
                 + " verification cannot authorize publication")
    if len(agreed) != 1:
        fail("the required records on pull request #" + number
             + " name different publish-branch heads ("
             + ", ".join(sorted(agreed)) + "), so no one tree carries both"
             + " a capture and a replay")
    sys.stdout.write(agreed.pop() + "\\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def proof_head_program_source() -> str:
    """The materialized program's exact bytes, with its one label substituted.

    A function rather than a module constant because the substitution is the
    whole guarantee: a reader comparing this against `published_head` must be
    able to see that the LABEL came from `PUBLISH_HEAD_LABEL` and not from a
    literal typed twice.
    """
    return _PROGRAM_SOURCE.replace("__LABEL__", PUBLISH_HEAD_LABEL).replace(
        "__VERDICTS__", repr(FACTORY_RECORD_VERDICTS)
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
