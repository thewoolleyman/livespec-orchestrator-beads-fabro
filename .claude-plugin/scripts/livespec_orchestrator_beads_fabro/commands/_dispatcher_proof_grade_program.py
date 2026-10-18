"""The per-assertion Proof of Done grade, as the SANDBOX performs it.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch" ->
"The stages" (v156) puts a command node `proof_grade` between a `verified`
`proof_verify` and `pr_refresh`: it reads "the newest `verified` record on the
pull request whose run identifier the Dispatcher attributes to this dispatch,
using the same record reader the acceptance pass grades with", and exits zero
exactly when every `factory_captured` assertion of the effective criteria reads
as reproduced from that record.

WHY THE NODE EXISTS AT ALL. `proof_verify` publishes its OWN verdict, and that
verdict is a sentence about the record rather than a property of it. Measured
2026-10-16 on `bd-ib-rszkjc`, merged as pull request 3130: the run published a
`verified` record for three assertions, every stage went green, the pull request
merged -- and the post-merge acceptance pass parked the item NEEDS_ATTENTION with
all three assertions pending a Proof of Done record. Attribution was NOT the
cause; replaying the shipped reader over the published comments finds the record
and attributes it to the run. The record simply carries NO `Reproduced:` line
inside any assertion section. It carries ONE record-wide line under a trailing
`## Comparison against the captured proofs` heading, and the reader is right to
ignore it: `_dispatcher_proof_record` records that letting an assertion absorb a
later or trailing section's verdict is the FAIL-OPEN direction. So the record was
ungradeable, the prompt already asked for the verdict per assertion, the agent
deviated, and nothing graded the record before the run advanced to merge.

WHY THE READER IS THE SHIPPED BYTES AND NOT A FRAGMENT. Every other materialized
program here composes a hand-written fragment of the record format, held equal to
the host reader by a test (`_dispatcher_carry_forward_record` records what a
second ACCOUNT of this format cost: a reasonable-looking line-two grep returning
NOTHING on both committed real payloads). A fragment would be wrong HERE in a way
no test can hold: the clause requires "the same record reader the acceptance pass
grades with", and the whole point of the node is that the sandbox's reading and
the acceptance pass's reading cannot disagree. So the prepare step writes the
package's own `_dispatcher_proof_record.py` and its one intra-package dependency
into the sandbox verbatim, with the package prefix stripped from their import
lines, and the program imports them. There is ONE reader and no twin.

WHY THE ASSERTIONS ARE PROJECTED RATHER THAN READ FROM THE RECORD. Judging a
record against the set of assertions the record happens to list is the same
fail-open the trailing-summary case is: an assertion the record omits is
invisible to any check that reads only the record. The `factory_captured`
assertions of the dispatch-time effective criteria are therefore projected into
the sandbox environment, base64-encoded so arbitrary item prose cannot terminate
a TOML string or a shell word, and a projection that is ABSENT or unreadable
fails the grade closed rather than grading against an empty set.

WHY THE FAILURE COUNT LIVES IN THE PUBLICATION STATE DIRECTORY. The clause says
the count "is kept by the run itself rather than read from an engine visit
counter", and `_dispatcher_publication_state` already owns the one directory that
is per clone, which is per sandbox, which is per run -- resolved through
`git rev-parse --git-path`, which is also what keeps a NESTED execution of the
repository's check suite from erasing the live counter of the stage running it.
The two FILENAMES are the grade's own rather than that module's, because they
are not state the publication stages hand to each other.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_provenance import (
    FACTORY_RUN_ID_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PROOF_GRADE_ASSERTIONS_ENV_VAR",
    "PROOF_GRADE_ASSERTIONS_MAX_BYTES",
    "PROOF_GRADE_FAILURE_CAP",
    "PROOF_GRADE_FAILURE_COUNT_FILENAME",
    "PROOF_GRADE_FINDING_FILENAME",
    "PROOF_GRADE_PROGRAM_FILENAME",
    "PROOF_GRADE_READER_DIRECTORY",
    "PROOF_GRADE_READER_MODULES",
    "factory_captured_assertions",
    "proof_grade_assertions_env_lines",
    "proof_grade_program_path_expansion",
    "proof_grade_program_prepare_steps_block",
    "proof_grade_program_source",
    "proof_record_reader_sources",
]

PROOF_GRADE_PROGRAM_FILENAME = "livespec-proof-grade.py"

# The directory the reader modules land in, BESIDE the program rather than at the
# plugins root. Isolation is the point: the root already carries materialized
# helpers under dash-bearing names no import can reach, and putting importable
# module names there would put them on the path of anything else that ever adds
# the root to `sys.path`.
PROOF_GRADE_READER_DIRECTORY = "livespec-proof-record-reader"

# The package modules whose SHIPPED BYTES travel into the sandbox: the record
# reader the acceptance pass grades with, and the one intra-package module it
# imports. Enumerated rather than discovered, because a discovery walk would
# ship whatever happened to sit beside them and an absent member would surface
# as an import error inside a stage rather than as a refusal here.
PROOF_GRADE_READER_MODULES = (
    "_dispatcher_proof_attachment.py",
    "_dispatcher_proof_record.py",
)

PROOF_GRADE_ASSERTIONS_ENV_VAR = "LIVESPEC_PROOF_GRADE_ASSERTIONS"

# The same bound the publication body carries, and for the same reason: the
# encoded payload rides an `execve` argument through a prepare-era projection,
# and base64 inflates by 4/3. An item whose factory assertions exceed it
# projects NOTHING, which the program reads as an unestablished question and
# fails closed on -- never as an empty set, which would advance every record.
PROOF_GRADE_ASSERTIONS_MAX_BYTES = 30000

# The run's own two grade files, inside the publication state directory. The
# COUNT is what `proof_grade_route` reads; the FINDING is what an operator reads
# when the third failure ends the run, and it is kept beside the count because a
# count with no cause names no remedy.
PROOF_GRADE_FAILURE_COUNT_FILENAME = "livespec-proof-grade-failures"
PROOF_GRADE_FINDING_FILENAME = "livespec-proof-grade-finding"

# The ratified bound: the third recorded failure routes the run to
# `non_converged`. Spelled here because the program's own corrupt-count arm
# reports a count AT the cap, so a counter nothing can compare routes to
# non-convergence rather than retrying for ever.
PROOF_GRADE_FAILURE_CAP = 3

# The one prefix that makes the package's modules intra-package imports. Stripped
# rather than rewritten, so the sandbox's `from _dispatcher_proof_attachment
# import ...` is the shipped line with its package qualifier removed and nothing
# else -- a rewrite could change which names cross the boundary.
_PACKAGE_PREFIX = "livespec_orchestrator_beads_fabro.commands."

_PROGRAM_SOURCE = '''"""The per-assertion Proof of Done grade, materialized by the Dispatcher.

Grades the newest `verified` record attributed to this dispatch through the
package's OWN reader modules, written beside this file by the same prepare step.
Do not edit this file in a sandbox: it is rewritten from
`_dispatcher_proof_grade_program` on every dispatch.
"""

import base64
import json
import os
import subprocess
import sys

ASSERTIONS_ENV_VAR = "__ASSERTIONS_ENV_VAR__"
RUN_ID_MARKER = "__RUN_ID_MARKER__"
READER_DIRECTORY = "__READER_DIRECTORY__"
STATE_GIT_PATH = "__STATE_GIT_PATH__"
FAILURE_COUNT_FILENAME = "__FAILURE_COUNT_FILENAME__"
FINDING_FILENAME = "__FINDING_FILENAME__"
FAILURE_CAP = __FAILURE_CAP__

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               READER_DIRECTORY))

from _dispatcher_proof_record import (  # noqa: E402
    VERDICT_VERIFIED,
    latest_proof_record,
    proof_records,
)


def run_text(argv):
    """One subprocess reading's stdout, stripped, or None when it would not answer."""
    result = subprocess.run(argv, capture_output=True, text=True, check=False,
                            stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def declared_assertions():
    """The factory_captured assertions the Dispatcher projected, or None.

    None is the UNESTABLISHED answer and is deliberately not the empty list: an
    absent or unreadable projection means which assertions this record owes a
    verdict for was never established, while an empty list is the real answer for
    an item declaring none.
    """
    payload = os.environ.get(ASSERTIONS_ENV_VAR)
    if not payload:
        return None
    try:
        decoded = json.loads(base64.b64decode(payload.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(decoded, list):
        return None
    if not all(isinstance(one, str) for one in decoded):
        return None
    return decoded


def attributed_run_ids():
    """Every identifier a record may carry and still be THIS dispatch's.

    The dispatch id in the clone's own config leads, because that is what the
    capture and replay stages actually stamp their records with: `$FABRO_RUN_ID`
    is unset inside a stage, so the provenance marker is the value every
    published record carries (`_dispatcher_proof_attribution`).
    """
    named = [run_text(["git", "config", "--get", RUN_ID_MARKER]) or "",
             os.environ.get("FABRO_RUN_ID") or ""]
    return tuple(dict.fromkeys(one for one in named if one))


def state_directory():
    """The run's own state directory, created, or None when it cannot be resolved."""
    path = run_text(["git", "rev-parse", "--git-path", STATE_GIT_PATH])
    if not path:
        return None
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return None
    return path


def recorded_failures(state):
    """The failures recorded for this run so far; a corrupt count reads AT the cap.

    Fail-closed in the one direction that matters: a count nothing can compare
    must not read as zero, because zero is what lets the retry loop run for ever.
    """
    try:
        with open(os.path.join(state, FAILURE_COUNT_FILENAME), encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return 0
    stripped = text.strip()
    return int(stripped) if stripped.isdigit() else FAILURE_CAP


def record_failure(state, finding):
    """Count this failure against the run, and keep its cause beside the count."""
    with open(os.path.join(state, FAILURE_COUNT_FILENAME), "w", encoding="utf-8") as handle:
        handle.write(str(recorded_failures(state) + 1) + "\\n")
    with open(os.path.join(state, FINDING_FILENAME), "w", encoding="utf-8") as handle:
        handle.write(finding + "\\n")


def pull_request_comments(number):
    """The pull request's comments in the shape the reader parses, or None."""
    payload = run_text(["gh", "pr", "view", number, "--json", "comments"])
    if payload is None:
        return None
    try:
        decoded = json.loads(payload)
    except ValueError:
        return None
    comments = decoded.get("comments") if isinstance(decoded, dict) else None
    return comments if isinstance(comments, list) else None


def attributed_verified_record(comments, run_ids):
    """The newest `verified` record this dispatch answers for, or None."""
    return latest_proof_record(
        records=proof_records(comments=[one for one in comments if isinstance(one, dict)]),
        verdict=VERDICT_VERIFIED,
        run_ids=tuple(run_ids),
    )


def ungraded_assertions(record, assertions):
    """Every assertion the record does not state as reproduced, in record order.

    `reproduced` is tri-state and BOTH of its non-True answers deny the advance:
    False is a verifier's refusal and None is an assertion the record says nothing
    readable about. The clause admits exactly one reading -- "every assertion
    reads as reproduced" -- so collapsing the two here would change nothing about
    the verdict and would lose the distinction the finding reports.
    """
    return [one for one in assertions if record.reproduced(assertion=one) is not True]


def grade(number):
    """The whole grade, as (exit code, the one line the stage record carries)."""
    assertions = declared_assertions()
    if assertions is None:
        return 1, ("LIVESPEC_PROOF_GRADE_ASSERTIONS_UNREADABLE: the Dispatcher "
                   "projected no readable " + ASSERTIONS_ENV_VAR + " value, so which "
                   "assertions this record owes a verdict for was never established; "
                   "failing closed rather than advancing on a record nobody graded")
    run_ids = attributed_run_ids()
    if not run_ids:
        return 1, ("LIVESPEC_PROOF_GRADE_NO_RUN_IDENTITY: neither this clone's "
                   + RUN_ID_MARKER + " provenance marker nor FABRO_RUN_ID names this "
                   "dispatch, so no record can be attributed to it; failing closed "
                   "rather than grading whichever verified record is newest")
    comments = pull_request_comments(number)
    if comments is None:
        return 1, ("LIVESPEC_PROOF_GRADE_COMMENTS_UNREADABLE: the comments of pull "
                   "request #" + number + " could not be read, so the record cannot be "
                   "graded")
    record = attributed_verified_record(comments, run_ids)
    if record is None:
        return 1, ("LIVESPEC_PROOF_GRADE_NO_RECORD: pull request #" + number + " carries "
                   "no verified Proof of Done record for " + " or ".join(run_ids)
                   + ", so there is nothing to grade")
    ungraded = ungraded_assertions(record, assertions)
    if ungraded:
        return 1, ("LIVESPEC_PROOF_GRADE_UNGRADEABLE: the verified record "
                   + record.url + " states no per-assertion prose Reproduced: verdict "
                   "for " + str(len(ungraded)) + " of " + str(len(assertions))
                   + " factory_captured assertions, so it does not grade them. A "
                   "record-wide summary line and a verdict printed inside a fenced "
                   "proof are deliberately not per-assertion evidence. Each "
                   "ungraded assertion: " + "; ".join(ungraded))
    return 0, ("LIVESPEC_PROOF_GRADE_GRADED: the verified record " + record.url
               + " states every one of this item's " + str(len(assertions))
               + " factory_captured assertions as reproduced, per assertion, in prose; "
                 "proceeding to pr_refresh")


def parse_argv(argv):
    """The one value the `proof_grade` node hands down, or None when it is absent.

    The node resolves the pull request from the publish branch itself, exactly as
    `pr_refresh_head` does, so the branch's environment name is spelled in the
    graph beside every other stage's reading of it rather than a second time
    here.
    """
    for index, token in enumerate(argv):
        if token == "--pull-request" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def main(argv):
    number = parse_argv(argv)
    if number is None:
        sys.stderr.write("LIVESPEC_PROOF_GRADE_USAGE: --pull-request is "
                         "required\\n")
        return 1
    state = state_directory()
    if state is None:
        sys.stderr.write("LIVESPEC_PROOF_GRADE_NO_STATE_DIR: this run's state "
                         "directory could not be resolved inside the clone, so a "
                         "grade failure could not be counted against the run; "
                         "failing closed rather than retrying unbounded\\n")
        return 1
    status, sentinel = grade(number)
    if status != 0:
        record_failure(state, sentinel)
    sys.stderr.write(sentinel + "\\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def factory_captured_assertions(*, item: WorkItem) -> tuple[str, ...]:
    """One item's `factory_captured` assertions, in Definition of Done order.

    Read off the SAME effective-criteria resolution the acceptance pass grades,
    so the set the sandbox checks a record against and the set the pass checks it
    against are one set. A legacy item declares no mode at all and therefore
    answers EMPTY, which is the right answer and not a shortfall: such an item is
    graded by merged-diff vocabulary rather than by a record.
    """
    return effective_criteria(item=item).factory_captured_assertions


def proof_grade_assertions_env_lines(*, item: WorkItem | None) -> str:
    """The `[environments.<id>.env]` line carrying the projected assertions.

    Empty for a caller holding no work-item -- a direct caller, exactly as the
    publication-metadata projection treats one -- and empty for a payload over
    its byte bound. Both absences are read by the program as an UNESTABLISHED
    question rather than as an empty set, so neither can advance a record.
    """
    if item is None:
        return ""
    payload = base64.b64encode(
        json.dumps(list(factory_captured_assertions(item=item))).encode("utf-8")
    ).decode("ascii")
    if len(payload) > PROOF_GRADE_ASSERTIONS_MAX_BYTES:
        return ""
    return f"{PROOF_GRADE_ASSERTIONS_ENV_VAR} = {json.dumps(payload)}\n"


def proof_record_reader_sources() -> tuple[tuple[str, str], ...]:
    """Each reader module's SHIPPED BYTES, as (filename, source), package-free.

    Read off the files beside this module rather than through an import, which is
    what makes them the shipped bytes rather than a rendering of them: the one
    transformation applied is the removal of the intra-package import prefix, so
    a sandbox import of `_dispatcher_proof_attachment` resolves the sibling file
    the same step wrote.
    """
    directory = Path(__file__).parent
    return tuple(
        (name, (directory / name).read_text(encoding="utf-8").replace(_PACKAGE_PREFIX, ""))
        for name in PROOF_GRADE_READER_MODULES
    )


def proof_grade_program_source() -> str:
    """The grade program's exact bytes, with every owned spelling substituted.

    A function rather than a constant for the reason `proof_head_program_source`
    gives: a reader must be able to SEE that the environment names, the
    provenance marker, the state directory and the failure cap came from the
    modules that own them, not from literals typed twice.
    """
    return (
        _PROGRAM_SOURCE.replace("__ASSERTIONS_ENV_VAR__", PROOF_GRADE_ASSERTIONS_ENV_VAR)
        .replace("__RUN_ID_MARKER__", FACTORY_RUN_ID_MARKER)
        .replace("__READER_DIRECTORY__", PROOF_GRADE_READER_DIRECTORY)
        .replace("__STATE_GIT_PATH__", PUBLICATION_STATE_GIT_PATH)
        .replace("__FAILURE_COUNT_FILENAME__", PROOF_GRADE_FAILURE_COUNT_FILENAME)
        .replace("__FINDING_FILENAME__", PROOF_GRADE_FINDING_FILENAME)
        .replace("__FAILURE_CAP__", str(PROOF_GRADE_FAILURE_CAP))
    )


def proof_grade_program_path_expansion() -> str:
    """The shell expansion the `proof_grade` node resolves the program through.

    PUBLIC and spelled once, for the reason `_dispatcher_sandbox_plugins` gives:
    a node resolving a DIFFERENT root than the prepare pass would find no program
    at all, and the failure would then read as a Dispatcher that never
    materialized one.
    """
    return f"{sandbox_plugins_root_expansion()}/{PROOF_GRADE_PROGRAM_FILENAME}"


def proof_grade_program_prepare_steps_block() -> str:
    """The prepare step that lands the program and its reader inside the sandbox.

    Every file is written through a heredoc with a QUOTED delimiter, so the shell
    expands nothing inside sources that legitimately carry dollar-bearing,
    shell-looking text -- the reader's own regular expressions contain `$` and
    backticks, and an unquoted delimiter would substitute them away while the
    step still succeeded.

    The reader lands BEFORE the program, which is a requirement rather than a
    preference: a sandbox given the program alone fails at its import line, in a
    stage whose refusal would then name the grade rather than the preparation.
    """
    root = sandbox_plugins_root_expansion()
    reader = f"{root}/{PROOF_GRADE_READER_DIRECTORY}"
    lines = [f'set -eu\nmkdir -p "{reader}"']
    for index, (name, source) in enumerate(proof_record_reader_sources()):
        delimiter = f"LIVESPEC_PROOF_RECORD_READER_{index}"
        lines.append(f"cat > \"{reader}/{name}\" <<'{delimiter}'\n{source}{delimiter}")
    delimiter = "LIVESPEC_PROOF_GRADE_PROGRAM"
    program = f"{root}/{PROOF_GRADE_PROGRAM_FILENAME}"
    lines.append(f"cat > \"{program}\" <<'{delimiter}'\n{proof_grade_program_source()}{delimiter}")
    return (
        "\n# --- Dispatcher-materialized per-assertion Proof of Done grade: the\n"
        "# --- acceptance pass's OWN record reader, shipped verbatim, so the grade\n"
        "# --- the run advances on and the grade the pass takes cannot disagree\n"
        "# --- (bd-ib-kcq6pu) ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(chr(10).join(lines))}\n"
    )
