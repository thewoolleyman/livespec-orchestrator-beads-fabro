"""The flag surface of every dispatcher subcommand that is NOT a dispatch.

The sibling of `_dispatcher_dispatch_args`, and split out of `dispatcher.py` for
the same reason that one was. The router owns `main`, the handler table and the
assembly of the subparsers; this module owns the per-subcommand ARGUMENT
DECLARATIONS of the check, credential-status and reconcile families. Between the
two modules every flag declaration lives beside its own concern and the router
declares none itself, which is what `_dispatcher_invoker.add_invoker_argument`
already established here: an argument GROUP is added back into whichever parser
needs it rather than being spelled out again per subcommand.

The declarations here are MOVED, not rewritten. Every flag, `dest` and default is
the one the router carried, because each `dest` is a name some handler reads off
the Namespace and an absent one surfaces as an `AttributeError` deep inside a
command rather than as a usage error at the parser.
"""

from __future__ import annotations

import argparse

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_command import (
    add_credential_selection_arguments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    add_invoker_argument,
)

__all__: list[str] = [
    "add_claude_cred_status_arguments",
    "add_codex_cred_refresh_arguments",
    "add_janitor_check_arguments",
    "add_ledger_check_arguments",
    "add_ledger_normalize_arguments",
    "add_reconcile_merged_arguments",
    "add_reconcile_runs_arguments",
    "add_spec_check_arguments",
]


def add_ledger_check_arguments(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def add_ledger_normalize_arguments(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    # `--gate` is the always-run pre-push mode: auto-heal-loud — it heals the
    # two safe transient remaps in place, prints each, and sets a fail-soft
    # exit-code contract (0 clean/healed / 1 residual drift / 2 could-not-check).
    # See `_dispatcher_ledger_gate.run_ledger_gate`.
    _ = parser.add_argument("--gate", dest="gate", action="store_true")


def add_spec_check_arguments(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    _ = parser.add_argument("--spec-root", dest="spec_root", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def add_codex_cred_refresh_arguments(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    add_credential_selection_arguments(parser=parser)


def add_claude_cred_status_arguments(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def add_janitor_check_arguments(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def add_reconcile_runs_arguments(*, parser: argparse.ArgumentParser) -> None:
    # `--factory` NARROWS the survey to one declared factory. Omitting it is
    # the correct default: reconciliation is an inventory question, and an
    # inventory taken of one factory says nothing about the others.
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument("--factory", dest="factory", default=None)
    _ = parser.add_argument("--fabro-bin", dest="fabro_bin", default=None)
    _ = parser.add_argument("--journal", dest="journal", default=None)
    _ = parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    add_invoker_argument(parser=parser)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def add_reconcile_merged_arguments(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument("--janitor", dest="janitor", default=None)
    _ = parser.add_argument("--journal", dest="journal", default=None)
    add_invoker_argument(parser=parser)
    _ = parser.add_argument(
        "--force",
        dest="force",
        action="store_true",
        help=(
            "bypass only the live-dispatch heartbeat refusal after confirming the "
            "original dispatcher process is dead"
        ),
    )
    _ = parser.add_argument(
        "--regrade",
        dest="regrade",
        action="store_true",
        help=(
            "re-grade an already-merged rework:pending item against its current "
            "effective acceptance criteria instead of refusing it; proceeds only "
            "when the merged PR resolves and its merge commit is an ancestor of the "
            "default branch, and leaves the item untouched on any non-PASS verdict"
        ),
    )
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
