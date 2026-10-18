"""Reading the factory, publishing the tree, and naming the ref on the item.

The IMPURE half of the tree preservation. `_dispatcher_preserved_tree_
disposition` decides and renders; everything that touches the world is here:
the run's event stream off the dispatch's own factory, the run-files read and
the four forge writes, the ledger append, and the journal rows.

IT RUNS BEFORE THE ITEM'S BLOCKED TRANSITION, which is the clause's own
ordering and not a convenience. The comment is the ONLY durable pointer at the
ref -- the dispatch result is read once, the journal lives in the `tmp/` tree
of whichever host ran the dispatch, and the factory prunes the run -- so a
comment written after a lifecycle write that failed would leave a ref nobody
can find, while a comment that cannot be written must still not prevent the
item from coming to rest.

EVERY FAILURE HERE IS FAIL-SOFT, AND THAT IS RATIFIED RATHER THAN LENIENT: "a
failed preservation MUST NOT change the dispatch outcome or its exit code". The
run has already ended, the item rests at `blocked` / `needs-human` either way,
and there is no decision left for a non-zero exit to inform. So an unreadable
factory, a refused forge write and a refused ledger append each leave a journal
row and return.

THE EVENT READ IS NOT ALLOWED TO DECIDE ANYTHING BY ITS FAILURE. A refused
`fabro events` yields `None`, which the trigger treats as a terminal patch
UNOBSERVED rather than absent, so the publication still happens -- a duplicate
preservation is recoverable and a missed one is not. Collapsing that onto an
empty record tuple would suppress the one publication the clause makes
mandatory, and it would do so silently, because an empty stream and an
unreadable one look identical at the trigger.

BOTH TRANSPORTS ARE BUILT FROM THE DISPATCH'S OWN RESOLVED FACTORY TARGET and
never from a default: a port built elsewhere reaches whichever server a default
names, which is the wrong-population trap this fleet's catalogue records against
a bare `fabro ps` -- and here it would publish ANOTHER run's tree under this
item's preservation ref.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree import publish_run_tree
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_disposition import (
    PreservedTreeDisposition,
    Publication,
    TerminatedRun,
    dispose_preserved_tree,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_RECORD_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_events import (
    fabro_event_records_from_stdout,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    FabroHttpTransport,
    UrllibFabroHttpTransport,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PRESERVED_TREE_UNREACHABLE_STAGE",
    "PreservationInputs",
    "preserve_checkpoint_failed_tree",
]

# The row for a terminal this preservation could not even ASK about, which is a
# different fact from one it asked about and declined: a run id or a server url
# the dispatch never recorded leaves no factory to read, so the trigger is never
# consulted and no `preserved-tree-skipped` reason could honestly be written.
PRESERVED_TREE_UNREACHABLE_STAGE = "preserved-tree-unreachable"

# The endings a preservation is owed for. A green run merged its work, so there
# is no unpreserved tree to publish and the four forge writes would be spent on
# every successful dispatch.
_TERMINAL_STATUSES = frozenset({"blocked", "failed"})

_EVENTS_TIMEOUT_SECONDS = 120.0

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
)


@dataclass(frozen=True, kw_only=True)
class PreservationInputs:
    """What this leg reads from outside the dispatch result, and through what.

    The journal rows are PASSED rather than re-read here, because the base
    commit comes out of them and the caller already holds the journal path it
    has been appending to all dispatch -- a second resolution of that path
    cannot be proven to agree with the first.

    Both transports default to the production ones, so the ordinary call site
    names neither; they are parameters at all so that every arm of the ratified
    clause is exercisable without a factory, a forge or a tenant.
    """

    journal_records: tuple[dict[str, object], ...]
    runner: CommandRunner | None = None
    transport: FabroHttpTransport | None = None


def preserve_checkpoint_failed_tree(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalWriter,
    inputs: PreservationInputs,
) -> None:
    """Publish a checkpoint-failed run's tree and name the ref on the item."""
    if outcome.status not in _TERMINAL_STATUSES:
        return
    run_id = outcome.fabro_run_id
    target = getattr(args, "fabro_factory_target", None)
    server = getattr(target, "server", None)
    server_url = server if isinstance(server, str) and server else None
    if run_id is None or server_url is None:
        journal.append(
            record={
                "stage": PRESERVED_TREE_UNREACHABLE_STAGE,
                "work_item_id": item.id,
                "reason": "missing-run-or-server",
                "run_id": run_id,
                "factory_server_url": server_url,
            }
        )
        return
    runner = inputs.runner if inputs.runner is not None else ShellCommandRunner()
    port = FabroPort(
        fabro_bin=str(args.fabro_bin),
        target=FabroTarget(server_url=server_url),
        runner=runner,
        cwd=repo,
    )
    disposition = dispose_preserved_tree(
        run=TerminatedRun(
            work_item_id=item.id,
            run_id=run_id,
            factory=str(getattr(target, "name", server_url)),
            failure_text=_failure_text(outcome=outcome),
            event_records=_event_records(port=port, run_id=run_id),
        ),
        journal_records=inputs.journal_records,
        publish=_publication(
            http=_http_port(server_url=server_url, transport=inputs.transport),
            runner=runner,
            repo=repo,
            work_item_id=item.id,
            run_id=run_id,
        ),
    )
    _record(repo=repo, item=item, journal=journal, disposition=disposition)


def _failure_text(*, outcome: DispatchOutcome) -> str:
    """Every text the ending could have named its checkpoint failure in.

    BOTH are read and joined rather than one being preferred, because the engine
    puts the sentence in different places on different builds: the classified
    cause on one, the rendered outcome detail on the other. The trigger's
    recognizer is unanchored, so a joined text costs nothing and a chosen one
    silently misses the ending on whichever build does not use that field --
    which suppresses the publication, the one direction this clause forbids.
    """
    return "\n".join(part for part in (outcome.fabro_failure_cause, outcome.detail) if part)


def _event_records(*, port: FabroPort, run_id: str) -> tuple[dict[str, object], ...] | None:
    """The run's event stream, or None for a read that did not work.

    `None` is load-bearing and is NOT an empty stream: the trigger reads it as a
    terminal patch unobserved rather than absent, and therefore still publishes.
    """
    result = port.events(run_id=run_id, timeout_seconds=_EVENTS_TIMEOUT_SECONDS)
    if result.command.exit_code != 0:
        return None
    records = fabro_event_records_from_stdout(stdout=result.command.stdout)
    return None if records is None else tuple(dict(record) for record in records)


def _http_port(*, server_url: str, transport: FabroHttpTransport | None) -> FabroHttpPort:
    """This factory's server-API face, which is the only route to the run's files."""
    return FabroHttpPort(
        target=FabroTarget(server_url=server_url),
        transport=transport if transport is not None else UrllibFabroHttpTransport(),
    )


def _publication(
    *,
    http: FabroHttpPort,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    run_id: str,
) -> Publication:
    """Bind the publication to this run, so the decision supplies only the base."""

    def publish(*, base_commit: str) -> PreservedTree | PublishFailure:
        return publish_run_tree(
            port=http,
            runner=runner,
            repo=repo,
            work_item_id=work_item_id,
            run_id=run_id,
            base_commit=base_commit,
        )

    return publish


def _record(
    *,
    repo: Path,
    item: WorkItem,
    journal: JournalWriter,
    disposition: PreservedTreeDisposition,
) -> None:
    """Journal the row, then append the comment -- in that order, on purpose.

    The ROW FIRST, because it is the record that cannot refuse: the tenant can
    be unreachable while the journal is a local append, so writing the comment
    first would leave a published ref with no record of it anywhere if the
    tenant declined. The comment is what SURVIVES, and the row is what proves
    the attempt.
    """
    journal.append(record=disposition.record)
    if disposition.body is None:
        if disposition.withheld_reason is not None:
            journal.append(
                record={
                    "stage": PRESERVED_TREE_RECORD_STAGE,
                    "work_item_id": item.id,
                    "reason": disposition.withheld_reason,
                }
            )
        return
    body = disposition.body
    written = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=item.id,
            body=body,
        ),
        exceptions=(*_LEDGER_WRITE_ERRORS, OSError),
    )
    if isinstance(written, AttemptFailure):
        journal.append(
            record={
                "stage": PRESERVED_TREE_RECORD_STAGE,
                "work_item_id": item.id,
                "reason": type(written.error).__name__,
            }
        )
