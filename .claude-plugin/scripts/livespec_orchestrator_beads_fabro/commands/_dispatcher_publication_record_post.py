"""The materialized program that posts a run's publication record.

`SPECIFICATION/contracts.md`, in its paragraph on a publication being bound to its
run on the pull request, has `publish_draft` and `pr_refresh` post one
`livespec-publication-record` comment after each push that moved the publish
branch. `_dispatcher_publication_record` is the READER of that comment; this
module is the WRITER.

WHY A MATERIALIZED PROGRAM RATHER THAN SHELL IN EACH NODE. Both stages need the
same comment, and the format is the one thing a reader and a writer must not
spell twice. The program is stdlib-only Python that the Dispatcher materializes
beside the push credential helper, with the marker and the field names
substituted in from the reader's own constants, so there is one spelling.

WHY IT NEVER FAILS THE STAGE. The contract says posting "MUST NOT change the
stage's outcome, its exit code or the head it pushed". Every failure therefore
ends in exit 0 after one line on standard error naming the run, the pushed commit
and the failed step, and a head the record never reached is attributed only by
the proof and journal records, or stays unattributed.

THE HEAD IT NAMES IS THE ONE THE CALLER PASSES, which each stage reads off its own
checkout AFTER the push succeeded, never the head the `janitor` passed. A push
that leaves the publish branch's tip unchanged (`--previous-tip` equal to
`--head`) posts nothing.

The comment is posted through the same `gh` the stage pushed with, which is the
Dispatcher's refreshing wrapper, so its forge author is the identity that made
the push: the GitHub App's bot login the consumer commits as
`dispatcher.publication_identity`.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_record import (
    PUBLICATION_RECORD_FIELDS,
    PUBLICATION_RECORD_MARKER,
)

__all__: list[str] = [
    "PUBLICATION_RECORD_POST_PROGRAM_RELPATH",
    "publication_record_post_program_source",
]

# Where the program lands below the gh-refresh root, beside `push_origin`.
PUBLICATION_RECORD_POST_PROGRAM_RELPATH = "bin/post_publication_record"

_PROGRAM_SOURCE = '''#!/usr/bin/env python3
"""Post one publication record on the item's pull request; never fail the stage."""

import datetime
import subprocess
import sys

MARKER = __MARKER__
FIELDS = __FIELDS__


def report(*, run, head, step, detail):
    sys.stderr.write(
        "LIVESPEC_PUBLICATION_RECORD_FAILED: run=" + (run or "unresolved")
        + " pushed=" + (head or "unresolved") + " step=" + step
        + " detail=" + detail.strip().replace("\\n", " ")[:300] + "\\n"
    )


def option(*, argv, name):
    """The value following `name`, or the empty string when it is absent."""
    if name in argv and argv.index(name) + 1 < len(argv):
        return argv[argv.index(name) + 1]
    return ""


def run_gh(*, argv, stdin=None):
    return subprocess.run(
        ["gh", *argv], input=stdin, capture_output=True, text=True, check=False
    )


def resolve_pull_request(*, branch):
    """The number of the open pull request for `branch`, or the empty string."""
    result = run_gh(
        argv=["pr", "list", "--head", branch, "--state", "open",
              "--json", "number", "--jq", ".[0].number"]
    )
    if result.returncode != 0:
        return "", result.stderr
    return result.stdout.strip(), ""


def record_body(*, run, head, number, stage, pushed_at):
    values = dict(zip(FIELDS, (run, head, number, stage, pushed_at)))
    return "\\n".join([MARKER] + [name + ": " + values[name] for name in FIELDS]) + "\\n"


def post(*, argv):
    stage = option(argv=argv, name="--stage")
    head = option(argv=argv, name="--head")
    run = option(argv=argv, name="--run-id")
    previous = option(argv=argv, name="--previous-tip")
    number = option(argv=argv, name="--pull-request").lstrip("#")
    branch = option(argv=argv, name="--branch")
    if not run:
        return report(run=run, head=head, step="run-id", detail="no run id was passed")
    if len(head) != 40:
        return report(run=run, head=head, step="pushed-head",
                      detail="the pushed commit is not a full commit id")
    if head == previous:
        sys.stderr.write(
            "LIVESPEC_PUBLICATION_RECORD_SKIPPED: the push left the publish branch's tip"
            " at " + head + ", so no record is posted\\n"
        )
        return None
    if not number:
        number, detail = resolve_pull_request(branch=branch)
        if not number:
            return report(run=run, head=head, step="pull-request-lookup",
                          detail=detail or "no open pull request for " + branch)
    pushed_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = record_body(run=run, head=head, number=number, stage=stage, pushed_at=pushed_at)
    result = run_gh(argv=["pr", "comment", number, "--body-file", "-"], stdin=body)
    if result.returncode != 0:
        return report(run=run, head=head, step="comment-post", detail=result.stderr)
    sys.stderr.write(
        "LIVESPEC_PUBLICATION_RECORD_POSTED: run=" + run + " head=" + head
        + " pull_request=#" + number + " stage=" + stage + "\\n"
    )
    return None


def main(argv):
    try:
        post(argv=argv)
    except Exception as error:  # the record must never change the stage's outcome
        report(run=option(argv=argv, name="--run-id"), head=option(argv=argv, name="--head"),
               step="unexpected-error", detail=type(error).__name__ + ": " + str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def publication_record_post_program_source() -> str:
    """The program's exact bytes, with the record format read off the reader's constants."""
    return _PROGRAM_SOURCE.replace("__MARKER__", repr(PUBLICATION_RECORD_MARKER)).replace(
        "__FIELDS__", repr(PUBLICATION_RECORD_FIELDS)
    )
