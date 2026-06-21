"""`orchestrator` — the one orchestrator-side contract CLI binary.

Per livespec/SPECIFICATION/contracts.md §"Orchestrator CLI contract —
the three named CLIs" and §"CLI shape conventions" (one binary per
side with subcommands; `--json` everywhere; stdin/stdout plus files
for payloads; the §"Lifecycle exit-code table" codes; explicit
project-root addressing), this module carries the three orchestrator
CLIs the consuming project's `.livespec.jsonc` `orchestrator` section
names in argv form:

  orchestrator.py spec-reader   [--project-root <path>] [--spec-target <path>]
                                [--category <name>] [--json]
  orchestrator.py gap-capture   --gaps-json <path|-> [--project-root <path>]
                                [--spec-target <path>]
                                [--spec-reader-cli <json-argv>]
                                [--dry-run] [--json]
  orchestrator.py drift-capture --drifts-json <path|->
                                --propose-change-cli <json-argv>
                                [--spec-reader-cli <json-argv>]
                                [--project-root <path>] [--spec-target <path>]
                                [--dry-run] [--json]

`<json-argv>` flags carry an injected reference CLI as a JSON array of
strings (the argv-form convention of the config naming), e.g.
`--propose-change-cli '["python3", "/path/to/propose_change.py"]'`.

Exit codes follow livespec's lifecycle exit-code table: 0 success,
2 usage error, 3 precondition error (missing payload file / spec tree
/ failed injected CLI), 4 wire-shape validation error.

Subcommand behavior lives in the sibling `_orchestrator_*` modules;
this module owns argument parsing, injected-argv parsing, and the
expected-error → exit-code mapping.
"""

import argparse
import sys
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._orchestrator_drift_capture import run_drift_capture
from livespec_orchestrator_beads_fabro.commands._orchestrator_gap_capture import run_gap_capture
from livespec_orchestrator_beads_fabro.commands._orchestrator_shared import (
    CliContext,
    InjectedCliError,
    PayloadInvalidError,
    PayloadMissingError,
    parse_cli_argv,
)
from livespec_orchestrator_beads_fabro.commands._orchestrator_spec_reader import run_spec_reader

__all__: list[str] = ["main"]

_EXIT_USAGE_ERROR = 2
_EXIT_PRECONDITION_ERROR = 3
_EXIT_VALIDATION_ERROR = 4


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    spec_root = (
        Path(args.spec_target) if args.spec_target is not None else project_root / "SPECIFICATION"
    )
    context = CliContext(project_root=project_root, spec_root=spec_root)
    try:
        return _dispatch(args=args, context=context)
    except PayloadMissingError as exc:
        _ = sys.stderr.write(f"ERROR: {exc}\n")
        return _EXIT_PRECONDITION_ERROR
    except PayloadInvalidError as exc:
        _ = sys.stderr.write(f"ERROR: {exc}\n")
        return _EXIT_VALIDATION_ERROR
    except InjectedCliError as exc:
        _ = sys.stderr.write(f"ERROR: {exc}\n")
        return _EXIT_PRECONDITION_ERROR


def _dispatch(*, args: argparse.Namespace, context: CliContext) -> int:
    if args.subcommand == "spec-reader":
        return run_spec_reader(
            spec_root=context.spec_root,
            category=args.category,
            as_json=args.as_json,
        )
    spec_reader_cli, ok = _optional_cli(raw=args.spec_reader_cli, flag="--spec-reader-cli")
    if not ok:
        return _EXIT_USAGE_ERROR
    if args.subcommand == "gap-capture":
        return run_gap_capture(
            gaps_json=args.gaps_json,
            context=context,
            spec_reader_cli=spec_reader_cli,
            dry_run=args.dry_run,
            as_json=args.as_json,
        )
    propose_change_cli = parse_cli_argv(raw=args.propose_change_cli, flag="--propose-change-cli")
    if propose_change_cli is None:
        return _EXIT_USAGE_ERROR
    return run_drift_capture(
        drifts_json=args.drifts_json,
        propose_change_cli=propose_change_cli,
        spec_reader_cli=spec_reader_cli,
        context=context,
        dry_run=args.dry_run,
        as_json=args.as_json,
    )


def _optional_cli(*, raw: str | None, flag: str) -> tuple[list[str] | None, bool]:
    """Parse an OPTIONAL injected-CLI flag; (argv-or-None, parse-ok)."""
    if raw is None:
        return None, True
    parsed = parse_cli_argv(raw=raw, flag=flag)
    if parsed is None:
        return None, False
    return parsed, True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orchestrator")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    spec_reader = subparsers.add_parser("spec-reader")
    _add_common(parser=spec_reader)
    _ = spec_reader.add_argument("--category", dest="category", default=None)
    gap_capture = subparsers.add_parser("gap-capture")
    _add_common(parser=gap_capture)
    _add_capture_common(parser=gap_capture)
    _ = gap_capture.add_argument("--gaps-json", dest="gaps_json", required=True)
    drift_capture = subparsers.add_parser("drift-capture")
    _add_common(parser=drift_capture)
    _add_capture_common(parser=drift_capture)
    _ = drift_capture.add_argument("--drifts-json", dest="drifts_json", required=True)
    _ = drift_capture.add_argument(
        "--propose-change-cli",
        dest="propose_change_cli",
        required=True,
    )
    return parser


def _add_common(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    _ = parser.add_argument("--spec-target", dest="spec_target", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def _add_capture_common(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--spec-reader-cli", dest="spec_reader_cli", default=None)
    _ = parser.add_argument("--dry-run", dest="dry_run", action="store_true")
