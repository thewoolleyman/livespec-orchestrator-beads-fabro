"""`/livespec-orchestrator-beads-fabro:detect-impl-gaps` thin-transport command.

CLI surface per `SPECIFICATION/contracts.md`:

  detect-impl-gaps [--spec-target <path>] [--project-root <path>] [--json]
                   [--since-version <vN>]

A HEADING-COVERAGE enumerator, not a spec→impl comparator: it reads the
live Specification's H2 headings via the Spec Reader and the repository's
heading-coverage map, and emits one gap per heading that no test
exercises. It never reads implementation state, so a returned gap-id
means "this heading has no exercising test", never "this heading's
behaviour is verified absent from the implementation".

It does NOT enumerate MUST/SHOULD clauses. A clause with no work-item is
the ordinary state of every ratified clause, and that signal surfaced 752
to 1,233 candidates per run in this repository without one completed
pass.

The skill is the canonical gap-detection surface for the plugin. Consumed
by livespec doctor's `gap-tracking-one-to-one` and `no-stale-gap-tied`
invariants via subprocess, and by the heavyweight `capture-impl-gaps`
sibling as its detection step. The heavyweight `implement` skill's
gap-tied closure verification is check-path-anchored and does NOT invoke
this skill: a gap-id identifies a heading, not the check that settles a
clause beneath it.

The skill is intrinsically non-mutating: no store writes, no user
prompts, no spec modifications.
"""

import argparse
import json
from pathlib import Path

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._heading_gaps import (
    HeadingGapScan,
    scan_heading_gaps,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = ["main"]

_EXIT_USAGE_ERROR = 2
_EXIT_PRECONDITION_ERROR = 3


def main(*, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="detect-impl-gaps")
    _ = parser.add_argument(
        "--spec-target",
        dest="spec_target",
        default=None,
        help="Path to the spec tree (default: SPECIFICATION/ under --project-root).",
    )
    _ = parser.add_argument(
        "--project-root",
        dest="project_root",
        default=None,
        help="Project root (default: current working directory).",
    )
    _ = parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help='Emit JSON `{"gap_ids": [...]}` instead of human-readable lines.',
    )
    _ = parser.add_argument(
        "--since-version",
        dest="since_version",
        default=None,
        help=(
            "Restrict the scan to files differing between this historical "
            "version (positive integer; the vNNN suffix) and the live spec. "
            "When omitted, scans every governed file."
        ),
    )
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    spec_root = (
        Path(args.spec_target) if args.spec_target is not None else project_root / "SPECIFICATION"
    )
    since_version: int | None = None
    if args.since_version is not None:
        parsed = _parse_since_version(raw=args.since_version)
        if parsed is None:
            parts: list[str] = [
                "ERROR: --since-version requires a positive integer",
                f" (got '{args.since_version}');",
                " accepted forms are 'v<N>' or '<N>' where N is a",
                " positive integer.\n",
            ]
            _ = write_stderr(text="".join(parts))
            return _EXIT_USAGE_ERROR
        since_version = parsed
    scan = scan_heading_gaps(
        spec_root=spec_root,
        project_root=project_root,
        since_version=since_version,
    )
    if not is_successful(scan):
        _ = write_stderr(text=f"ERROR: {unsafe_perform_io(scan.failure())}\n")
        return _EXIT_PRECONDITION_ERROR
    result = unsafe_perform_io(scan.unwrap())
    if args.as_json:
        _write_json(scan=result)
    else:
        _write_human(scan=result)
    _write_findings(scan=result)
    return 0


def _parse_since_version(*, raw: str) -> int | None:
    """Parse a `--since-version` argument to a positive integer.

    Accepts either `v<N>` (e.g. `v082`) or a bare `<N>` (e.g. `82`).
    Returns None if the value is not a positive integer.
    """
    candidate = raw.lstrip("vV") if raw.startswith(("v", "V")) else raw
    if not candidate.isdigit():
        return None
    value = int(candidate)
    if value <= 0:
        return None
    return value


def _write_json(*, scan: HeadingGapScan) -> None:
    """Emit the ratified one-key machine envelope.

    `gap_ids` is the ONLY key: doctor's cross-boundary invariants read this
    stdout, so anything else a run has to say belongs on stderr.
    """
    payload = {"gap_ids": sorted(gap.gap_id for gap in scan.gaps)}
    _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_findings(*, scan: HeadingGapScan) -> None:
    """Surface every defective registry row on stderr.

    STDERR in both output modes, and that is the whole reason this is its own
    emitter: the machine envelope is the ratified one-key object doctor reads,
    so a finding folded into it would be a wire-format change for a consumer
    that only wants gap-ids — while dropping it would report a dangling entry
    as the clean absence the contract forbids.
    """
    for finding in scan.findings:
        _ = write_stderr(text=finding.render() + "\n")


def _write_human(*, scan: HeadingGapScan) -> None:
    if not scan.gaps:
        _ = write_stdout(text="(no uncovered headings detected)\n")
        return
    for gap in scan.gaps:
        line = f"{gap.spec_root}/{gap.spec_file} > {gap.heading}  [{gap.gap_id}]\n"
        _ = write_stdout(text=line)
