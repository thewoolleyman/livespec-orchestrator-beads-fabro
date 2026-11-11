"""_workflow_package_measure — render one repository's dispatch package and size every file.

The private half of `materialized_workflow_toml_size`, split out along its own
seam: this module answers "what does the Dispatcher hand Fabro for this
repository, and how big is each piece", and the check decides which repositories
to ask and what counts as a refusal.

THE PACKAGE IS WHAT FABRO COLLECTS. A dispatch copies the selected workflow's
committed directory (graph, prompts, anything else in it) into a per-dispatch
payload directory and overwrites its `workflow.toml` with the rendered overlay.
Fabro caps EACH file at 524,288 bytes and the package at 2 MiB and 512 files, so
every file is measured, not only the overlay. The overlay is rendered through
`render_run_config_overlay` and the graph through `render_workflow_graph` with
the repository's own node timeouts; the graph's literal ACP commands are not
rendered, because resolving them reads the routing table, and they add a few
hundred bytes per ACP node to a file far under its cap.

TWO SUBJECTS PER WORKFLOW. The REPRESENTATIVE case derives everything item-shaped
from one item whose description is exactly 20,480 bytes, through the same
`publication_metadata_for` and `dod_gate_subject` a dispatch calls. The WORST case
hands the overlay a Definition-of-Done subject of `WORST_CASE_SUBJECT_BYTES` read
from this repository's own committed specification prose, which compresses like
the measured subjects do (they are mostly referenced spec sections). It is sized
from the largest live subject block measured across the fleet's ready and backlog
items on 2026-11-10, 120,466 bytes (bd-ib-qshcwc's 110,569 bytes is the largest
single subject), plus a third. The specification states no bound on a subject's
riders, so the check measures that margin rather than enforcing a limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_projection import (
    CredentialUseProjection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_subject import (
    dod_gate_subject,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_build import HelperSource
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    RELEASE_REPOSITORY_URL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_prompt_variables,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan import (
    workflow_payload_dir,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    SiblingClones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (
    resolve_repo_integration_contract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    cc_otel_overlay_env,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    proof_store_env_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    publication_metadata_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_worktree_pack import (
    fleet_toolchain_is_the_sandbox_gate_premise,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import node_timeouts_from_block
from livespec_orchestrator_beads_fabro.commands._workflow_variants import (
    RESERVED_WORKFLOW_NAME,
    workflow_registry,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "GOAL_BYTES",
    "RESERVED_RELPATH",
    "WORST_CASE_SUBJECT_BYTES",
    "Measurement",
    "measure_repository",
    "representative_item",
]

GOAL_BYTES = 20_480
WORST_CASE_SUBJECT_BYTES = 160_000
RESERVED_RELPATH = Path(".fabro") / "workflows" / RESERVED_WORKFLOW_NAME / "workflow.toml"
_ITEM_ID = "livespec-dev-tooling-zzzzzz"
_DISPATCH_ID = "01M5ZZZZZZZZZZZZZZZZZZZZZZ"
# The in-sandbox root the overlay clones siblings under, as `_dispatcher_sibling_clones`
# projects it; only its length reaches the measurement.
_SANDBOX_CLONES_ROOT = "/livespec-siblings"
# The build the measured overlay's helper manifest names. Only its LENGTH reaches
# the measurement, so a fixed full-length commit stands in for the installed one,
# and the check reads no install record and no git state.
_HELPER_SOURCE = HelperSource(repository=RELEASE_REPOSITORY_URL, commit="0" * 40)


@dataclass(frozen=True, kw_only=True)
class Measurement:
    """One package file's size (`None` when the run config does not render)."""

    repository: str
    workflow: str
    case: str
    file: str
    size: int | None


def representative_item() -> WorkItem:
    """A work item whose description is exactly `GOAL_BYTES` long, Definition of Done first."""
    bullets = "".join(
        f"- Assertion {index} names one observable behaviour of the delivered change.\n"
        for index in range(12)
    )
    head = (
        "## Definition of Done\n\nReferences: ## Self-contained plugin dispatch\n\n"
        f"{bullets}\n## Context\n\n"
    )
    sentence = "The representative dispatch carries ordinary prose of a measured length. "
    body = (head + sentence * (GOAL_BYTES // len(sentence) + 1)).encode()[:GOAL_BYTES]
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A representative work item title of the length the fleet's titles run to" * 2,
        description=body.decode(),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-10T00:00:00+00:00",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        acceptance_criteria=None,
    )


def _worst_case_subject(*, prose: Path) -> str:
    data = prose.read_bytes()
    return (data * (WORST_CASE_SUBJECT_BYTES // len(data) + 1))[:WORST_CASE_SUBJECT_BYTES].decode(
        "utf-8", "ignore"
    )


def _workflows(*, repository: Path, bundled: Path) -> list[tuple[str, Path]]:
    """The reserved workflow this repository dispatches, then each registered variant."""
    own = repository / RESERVED_RELPATH
    registry = workflow_registry(block=dispatcher_block(cwd=repository))
    return [(RESERVED_WORKFLOW_NAME, own if own.is_file() else bundled)] + [
        (name, repository / declared / "workflow.toml")
        for name, declared in sorted(registry.items())
    ]


def _overlay(
    *, repository: Path, committed: Path, siblings: SiblingClones, subject: str | None
) -> str | None:
    item = representative_item()
    contract = resolve_repo_integration_contract(
        config_text=(repository / ".livespec.jsonc").read_text(encoding="utf-8"),
        default_branch="master",
    )
    return render_run_config_overlay(
        committed_text=committed.read_text(encoding="utf-8"),
        workflow_dir=committed.parent.resolve(),
        token="t" * 55,
        github_token="g" * 44,
        siblings=siblings,
        otel_env=cc_otel_overlay_env(
            work_item_id=_ITEM_ID,
            dispatch_id=_DISPATCH_ID,
            endpoint="http://host.docker.internal:4318",
        ),
        codex_auth_snapshot="c" * 47,
        codex_otel_config="o" * 291,
        credential_use=CredentialUseProjection(
            deadline_epoch=1_799_999_999,
            credential_expiry_epoch=1_799_999_999,
            required_remaining_seconds=999_999,
        ),
        graph_override=workflow_payload_dir(work_item_id=_ITEM_ID) / "workflow.fabro",
        dispatch_id=_DISPATCH_ID,
        proof_store_env=proof_store_env_lines(
            repo=repository, work_item_id=_ITEM_ID, rendering="inline"
        ),
        prepare_inputs=contract_prompt_variables(resolved=contract),
        provision_worktree_pack=fleet_toolchain_is_the_sandbox_gate_premise(resolved=contract),
        helper_source=_HELPER_SOURCE,
        publication_metadata=publication_metadata_for(item=item),
        dod_gate_subject=(
            dod_gate_subject(item=item, repo=repository, comments=())
            if subject is None
            else subject
        ),
    )


def _graph_size(*, repository: Path, graph: Path) -> int:
    """The graph's size with this repository's node timeouts rendered in, where they render."""
    text = graph.read_text(encoding="utf-8")
    timeouts = node_timeouts_from_block(block=dispatcher_block(cwd=repository))
    rendered = (
        text
        if isinstance(timeouts, str)
        else render_workflow_graph(committed_text=text, timeouts=timeouts)
    )
    return len((text if isinstance(rendered, str) else rendered.text).encode("utf-8"))


def measure_repository(
    *,
    repository: Path,
    name: str,
    siblings: tuple[str, ...],
    owner: str,
    bundled: Path,
    prose: Path,
) -> list[Measurement]:
    """Every file of every package `repository` dispatches, for both subject cases."""
    clones = SiblingClones(
        owner=owner,
        repos=tuple(sibling for sibling in siblings if sibling != name),
        clones_root=_SANDBOX_CLONES_ROOT,
    )
    measurements: list[Measurement] = []
    for workflow, committed in _workflows(repository=repository, bundled=bundled):
        directory = committed.parent
        others = {
            path.relative_to(directory).as_posix(): path.stat().st_size
            for path in sorted(directory.rglob("*"))
            if path.is_file() and path.name != "workflow.toml"
        }
        others["workflow.fabro"] = _graph_size(
            repository=repository, graph=directory / "workflow.fabro"
        )
        for case, subject in (
            ("representative", None),
            ("worst-case", _worst_case_subject(prose=prose)),
        ):
            rendered = _overlay(
                repository=repository, committed=committed, siblings=clones, subject=subject
            )
            files = {"workflow.toml": None if rendered is None else len(rendered.encode("utf-8"))}
            files.update(others)
            measurements.extend(
                Measurement(repository=name, workflow=workflow, case=case, file=file, size=size)
                for file, size in files.items()
            )
    return measurements
