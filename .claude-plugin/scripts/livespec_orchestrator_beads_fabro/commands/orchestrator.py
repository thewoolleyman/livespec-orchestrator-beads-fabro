"""`orchestrator` — the one orchestrator-side contract CLI binary.

Per livespec/SPECIFICATION/contracts.md (one binary per
side with subcommands; `--json` everywhere; stdin/stdout plus files
for payloads; the exit-code table codes; explicit
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
  orchestrator.py ledger-intent-scan --judge-cli <json-argv>
                                [--since-version <vN>]
                                [--coverage-point <value>]
                                [--project-root <path>] [--spec-target <path>]
                                [--json]

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
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._ledger_intent_cut import parse_spec_version
from livespec_orchestrator_beads_fabro.commands._orchestrator_drift_capture import run_drift_capture
from livespec_orchestrator_beads_fabro.commands._orchestrator_gap_capture import run_gap_capture
from livespec_orchestrator_beads_fabro.commands._orchestrator_ledger_intent import (
    run_ledger_intent_scan,
)
from livespec_orchestrator_beads_fabro.commands._orchestrator_shared import (
    CliContext,
    InjectedCliError,
    PayloadInvalidError,
    PayloadMissingError,
    parse_cli_argv,
)
from livespec_orchestrator_beads_fabro.commands._orchestrator_spec_reader import run_spec_reader
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = ["main"]

_EXIT_USAGE_ERROR = 2
_EXIT_PRECONDITION_ERROR = 3
_EXIT_VALIDATION_ERROR = 4


def main(*, argv: list[str] | None = None) -> int:
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
        _ = write_stderr(text=f"ERROR: {exc}\n")
        return _EXIT_PRECONDITION_ERROR
    except PayloadInvalidError as exc:
        _ = write_stderr(text=f"ERROR: {exc}\n")
        return _EXIT_VALIDATION_ERROR
    except InjectedCliError as exc:
        _ = write_stderr(text=f"ERROR: {exc}\n")
        return _EXIT_PRECONDITION_ERROR


def _dispatch(*, args: argparse.Namespace, context: CliContext) -> int:
    if args.subcommand == "spec-reader":
        return run_spec_reader(
            spec_root=context.spec_root,
            category=args.category,
            as_json=args.as_json,
        )
    if args.subcommand == "ledger-intent-scan":
        return _dispatch_ledger_intent(args=args, context=context)
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


def _dispatch_ledger_intent(*, args: argparse.Namespace, context: CliContext) -> int:
    """The ledger-intent-scan arm, in its own function.

    Extracted so `_dispatch` stays within the return-count ceiling rather than
    by raising it: the arm's own injected-CLI parse is a second refusal, and the
    subcommand surface grows one arm per ratified CLI.
    """
    judge_cli = parse_cli_argv(raw=args.judge_cli, flag="--judge-cli")
    if judge_cli is None:
        return _EXIT_USAGE_ERROR
    since_version: int | None = None
    if args.since_version is not None:
        since_version = parse_spec_version(raw=args.since_version)
        if since_version is None:
            _ = write_stderr(
                text=(
                    "ERROR: --since-version requires a positive integer (got "
                    f"{args.since_version!r}); accepted forms are 'v<N>' and '<N>'.\n"
                ),
            )
            return _EXIT_USAGE_ERROR
    return run_ledger_intent_scan(
        context=context,
        judge_cli=judge_cli,
        since_version=since_version,
        coverage_point=args.coverage_point,
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
    ledger_intent = subparsers.add_parser("ledger-intent-scan")
    _add_common(parser=ledger_intent)
    _ = ledger_intent.add_argument("--judge-cli", dest="judge_cli", required=True)
    _ = ledger_intent.add_argument("--since-version", dest="since_version", default=None)
    _ = ledger_intent.add_argument("--coverage-point", dest="coverage_point", default=None)
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
