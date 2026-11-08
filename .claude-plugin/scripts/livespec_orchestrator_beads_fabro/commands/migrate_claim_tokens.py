"""`migrate-claim-tokens` — the sanctioned claim-token migration pass.

The orchestrator-PRIVATE maintenance command contracts.md's claim-token rule
requires to run on a tenant BEFORE `dispatcher.claim_tokens` is committed
`true` there: it names a fresh open current token on every non-closed item that
names no open token, and leaves every item that already names one unchanged.

IT SURVEYS UNLESS THE OPERATOR ATTESTS. The pass MUST run while every claim
writer of the tenant is stopped: every Dispatcher, intake, the human valves and
reconciliation. Those writers may run on other hosts and share nothing with
this process but the Beads server, so this command cannot measure that they are
stopped; `--confirm-claim-writers-stopped` is the operator saying so. Without
the flag nothing is written and the items that would be named are listed.

THE EXIT CODE IS THE CUTOVER PRECONDITION. Exit 0 means every non-closed item
this run read names an open token, in either mode; exit 1 means some item does
not yet, whether because the run was a survey or because an item was held. So
the same command, run again, both finishes an interrupted pass and proves it
finished.

What the pass decides and writes lives in `_store_claim_token_migration`; this
module is the argument parsing, the report and the exit code.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_claim_token_migration import (
    ClaimTokenMigrationReport,
    migrate_claim_tokens,
)
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = ["CONFIRM_FLAG", "main", "render_report"]

CONFIRM_FLAG = "--confirm-claim-writers-stopped"

_EXIT_COMPLETE = 0
_EXIT_INCOMPLETE = 1


def main(*, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate-claim-tokens",
        description=(
            "Name a fresh open claim token on every non-closed item of one tenant "
            "that names no open token. Idempotent: an item already naming an open "
            "token is left unchanged, so an interrupted pass is finished by running "
            f"it again. Writes only with {CONFIRM_FLAG}; without it, surveys. "
            "Exit 0 means every non-closed item names an open token."
        ),
    )
    _ = parser.add_argument("--work-items-path", dest="work_items_path", default=None)
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    _ = parser.add_argument(
        CONFIRM_FLAG,
        dest="writers_stopped",
        action="store_true",
        help=(
            "Attest that every claim writer of this tenant is stopped: every "
            "Dispatcher, intake, the human valves and reconciliation, on every host."
        ),
    )
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    config = resolve_store_config(cwd=project_root, work_items_arg=args.work_items_path)
    report = migrate_claim_tokens(
        client=make_beads_client(config=config), apply=args.writers_stopped
    )
    _ = write_stdout(text=render_report(report=report))
    return _EXIT_COMPLETE if report.complete else _EXIT_INCOMPLETE


def render_report(*, report: ClaimTokenMigrationReport) -> str:
    """Render one run as the operator reads it: mode, each item, the verdict."""
    mode = "applied" if report.applied else "survey only, nothing written"
    lines = [
        f"migrate-claim-tokens: {mode}",
        f"named a fresh open token: {len(report.named)}",
        *(f"  {item_id} -> {token_id}" for item_id, token_id in report.named),
        f"already naming an open token (unchanged): {len(report.unchanged)}",
        f"naming no open token (not written): {len(report.unnamed)}",
        *(f"  {item_id}" for item_id in report.unnamed),
        f"held: {len(report.held)}",
        *(f"  {item_id}: {reason}" for item_id, reason in report.held),
        _verdict_line(report=report),
    ]
    return "\n".join(lines) + "\n"


def _verdict_line(*, report: ClaimTokenMigrationReport) -> str:
    if report.complete:
        return "result: complete - every non-closed item names an open claim token"
    if report.applied:
        return "result: incomplete - run the pass again to settle the held items"
    return (
        "result: incomplete - stop every claim writer of this tenant (every "
        "Dispatcher, intake, the human valves and reconciliation), then run "
        f"again with {CONFIRM_FLAG}"
    )
