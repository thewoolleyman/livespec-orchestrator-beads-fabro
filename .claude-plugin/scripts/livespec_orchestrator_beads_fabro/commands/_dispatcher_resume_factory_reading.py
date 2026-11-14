"""Asking a resume's factory about the earlier run of one item.

Split out of `_dispatcher_resume_observation` by cohesion: that module GATHERS the
three measurements a resume grades (ledger, forge, factory), and this is the
factory half -- one `fabro ps` and, only when the factory still holds the earlier
run, one `fabro inspect`. Its public entry point is `factory_reading`; the target
resolution it needs stays private here, because only this question uses it.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    NON_TERMINAL_STATUS_KINDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    LiveRun,
    live_runs_from_pairs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_run_record import (
    executing_node_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_verify_ending import (
    proof_verify_ended_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    RUN_SUCCEEDED,
    run_state_from_inventory,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroCommand,
    FabroPort,
    FabroTarget,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import journaled_run_ids
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "FactoryReading",
    "factory_reading",
]

_PS_TIMEOUT_SECONDS = 60.0
_INSPECT_TIMEOUT_SECONDS = 60.0
_FACTORY_READ_WRAPPER_ENV = "LIVESPEC_FACTORY_READ_WRAPPER"
_LIVENESS_READ_STAGE = "factory-liveness-read"
_HOST_WRAPPER_SOURCE = "host-wrapper"
_CLIENT_DEFAULT_SOURCE = "client-default"
_FACTORY_READ_SHELL = (
    'factory="$1"; server="$2"; shift 2; '
    'token="$(printenv "FABRO_DEV_TOKEN__$factory")" || exit 1; '
    '"$1" auth login --dev-token "$token" --server "$server" >/dev/null || exit $?; '
    'exec "$@"'
)


@dataclass(frozen=True, kw_only=True)
class FactoryReading:
    """What one factory answered about the earlier run of one item.

    `observed` false means the factory could not be asked. It is deliberately not
    the same value as an answering factory holding nothing alive, which carries
    the same empty `live_runs`: one authorizes a resume, the other refuses it.

    `executing_node` is `None` both when the factory no longer holds the run and
    when it holds it but names no stage, because the clause gives those one
    treatment — the verdict of the latest record decides instead.

    `earlier_run_succeeded` is the factory's own report that the earlier run
    ended `succeeded`. It is graded by the stranded-claim grader's reading of the
    listing, so a resume refusal and `reconcile-runs` agree on which claims the
    latter holds as `run-succeeded`.

    `proof_verify_ended` is the factory record's own account that the earlier run
    approved a capture and then ended at `proof_verify` posting no record. It is
    separate from `executing_node` because such a run names no running stage: it
    took a terminal node, so `executing_node` is `None` for it.
    """

    observed: bool
    live_runs: tuple[LiveRun, ...]
    executing_node: str | None
    earlier_run_succeeded: bool = False
    proof_verify_ended: bool = False


@dataclass(frozen=True, kw_only=True)
class _FactoryCredentialRunner:
    """Run one factory read in the host wrapper that owns its credential.

    The Dispatcher can be started below a sealed tenant wrapper, whose child
    intentionally has no ``FABRO_*`` settings. The host launcher supplies the
    default-wrapper pathname as a non-secret command operand; this runner asks
    that wrapper to resolve the named factory's token itself, logs the client
    in inside that child, then performs the read. The tenant wrapper therefore
    never receives a factory address or credential.
    """

    runner: CommandRunner
    wrapper: str
    factory_name: str
    server: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        """Authenticate and execute the original read inside the default wrapper."""
        _ = env
        return self.runner.run(
            argv=[
                self.wrapper,
                "--",
                "sh",
                "-ec",
                _FACTORY_READ_SHELL,
                "factory-read",
                self.factory_name,
                self.server,
                *argv,
            ],
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            stdin=stdin,
        )


def factory_reading(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal_path: Path,
    earlier_run_id: str | None,
    runner: CommandRunner,
) -> FactoryReading:
    """Ask the resolved factory which runs of this item live, and where the earlier one was.

    The factory target is read off `args` the way every other post-selection seam
    reads it — `dispatch_preamble` pins it before this is reached — and an absent
    one degrades to the client's own default rather than raising.
    """
    port = FabroPort(
        fabro_bin=args.fabro_bin,
        target=_factory_target(args=args),
        runner=_factory_read_runner(args=args, runner=runner),
        cwd=repo,
    )
    ps = port.ps(timeout_seconds=_PS_TIMEOUT_SECONDS)
    JournalFile(path=journal_path).append(
        record=_liveness_read_record(
            args=args,
            item=item,
            earlier_run_id=earlier_run_id,
            command=ps.command,
        )
    )
    if ps.command.exit_code != 0:
        return FactoryReading(observed=False, live_runs=(), executing_node=None)
    journaled_ids = journaled_run_ids(
        records=read_journal_records(journal_path=journal_path), work_item_id=item.id
    )
    journaled = frozenset(journaled_ids)
    claimed_run_id = (
        earlier_run_id if earlier_run_id is not None else next(iter(reversed(journaled_ids)), None)
    )
    attributed = [run for run in ps.runs if run.run_id in journaled or run.work_item_id == item.id]
    live = live_runs_from_pairs(
        pairs=[
            (run.run_id, run.status_kind or "unknown")
            for run in attributed
            if run.status_kind in NON_TERMINAL_STATUS_KINDS
        ]
    )
    held = earlier_run_id is not None and any(run.run_id == earlier_run_id for run in ps.runs)
    succeeded = (
        claimed_run_id is not None
        and run_state_from_inventory(
            surveyed=True,
            status_kinds={run.run_id: run.status_kind for run in ps.runs},
            run_id=claimed_run_id,
        )
        == RUN_SUCCEEDED
    )
    if not held:
        # An authoritative not-found observes the run as not live and sends the
        # stage question to the verdict fallback. Asking `inspect` anyway would
        # spend a round trip to learn what `ps` already answered, and a failing
        # `inspect` there would read as an outage rather than as the answer it is.
        return FactoryReading(
            observed=True, live_runs=live, executing_node=None, earlier_run_succeeded=succeeded
        )
    inspected = port.inspect(
        run_id=earlier_run_id if earlier_run_id is not None else "",
        timeout_seconds=_INSPECT_TIMEOUT_SECONDS,
    )
    return FactoryReading(
        observed=True,
        live_runs=live,
        executing_node=executing_node_from_payload(payload=inspected.payload),
        earlier_run_succeeded=succeeded,
        proof_verify_ended=proof_verify_ended_from_payload(payload=inspected.payload),
    )


def _liveness_read_record(
    *,
    args: argparse.Namespace,
    item: WorkItem,
    earlier_run_id: str | None,
    command: FabroCommand,
) -> dict[str, object]:
    """The one row a recovery-routing factory read leaves in the dispatch journal.

    It names the factory, its address, the run looked for, where the credential
    came from and the verdict, so a canary can prove the read ran and a later
    diagnosis of a credential fault has the failing exit code and message. The
    credential source is the NAME of the host wrapper's `FABRO_DEV_TOKEN__<factory>`
    variable, never a value, and never anything read from the tenant's wrapper.
    """
    target = getattr(args, "fabro_factory_target", None)
    factory = getattr(target, "name", "default")
    wrapped = os.environ.get(_FACTORY_READ_WRAPPER_ENV, "") != ""
    failed = command.exit_code != 0
    return {
        "stage": _LIVENESS_READ_STAGE,
        "work_item_id": item.id,
        "factory": factory,
        "server": getattr(target, "server", None),
        "earlier_run_id": earlier_run_id,
        "credential_source": (
            f"{_HOST_WRAPPER_SOURCE}:FABRO_DEV_TOKEN__{factory}"
            if wrapped
            else _CLIENT_DEFAULT_SOURCE
        ),
        "verdict": "unobservable" if failed else "observed",
        "exit_code": command.exit_code,
        "failure": command.stderr.strip() if failed else None,
    }


def _factory_target(*, args: argparse.Namespace) -> FabroTarget:
    """The resolved factory, or the client's own default when none was pinned."""
    target = getattr(args, "fabro_factory_target", None)
    return FabroTarget(
        server_url=getattr(target, "server", None),
        dev_token=getattr(target, "dev_token", None),
    )


def _factory_read_runner(*, args: argparse.Namespace, runner: CommandRunner) -> CommandRunner:
    """Use the host default wrapper for factory reads when the launcher supplied it."""
    wrapper = os.environ.get(_FACTORY_READ_WRAPPER_ENV, "")
    if wrapper == "":
        return runner
    target = getattr(args, "fabro_factory_target", None)
    return _FactoryCredentialRunner(
        runner=runner,
        wrapper=wrapper,
        factory_name=getattr(target, "name", "default"),
        server=getattr(target, "server", "") or "",
    )
