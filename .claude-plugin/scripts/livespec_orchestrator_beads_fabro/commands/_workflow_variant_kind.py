"""What KIND of work a registered workflow variant does, read off its own file.

WHY THE KIND LIVES WITH THE VARIANT AND NOT IN THE REGISTRY ENTRY.
`SPECIFICATION/contracts.md` section "Grooming and slice-size calibration" ->
"Consensus-gated automated groom cut" rules that the reserved
`implement-work-item` workflow MUST NOT groom and that a groom variant MUST
NOT implement. That is a property of the GRAPH -- which nodes it runs, that
its propose phase files nothing and terminates at a needs-human outcome -- not
of the line in `dispatcher.workflows` that names a directory. A registry entry
is one repository's naming of a directory; the same directory vendored into a
second repository under a second name has the same kind either way, and a kind
stated in the registry could disagree with the graph it names with nothing in
the run to catch it.

WHY THE DECLARATION RIDES `[run.inputs]` RATHER THAN THE `[workflow]` TABLE.
`[workflow]` is fabro's own field set, and whether the pinned engine tolerates
a key it does not define is not measurable from this repository -- a run
config is only ever parsed by the engine, and no engine build is reachable
from a dispatched sandbox's checks. `[run.inputs]` is measurably a free-form
string map: this plugin's own bundled run config declares fifteen names of its
own choosing there, and the Dispatcher already scans exactly that table for
two other input questions. Declaring the kind where the file is known to
accept arbitrary names keeps a mis-guess about fabro's schema from breaking
every dispatch of a variant, and it lets a groom variant's own graph read
`inputs.workflow_kind` if it ever needs to.

WHY AN UNDECLARED KIND READS AS `implement`, in both of the two ways a
declaration can be missing. Every variant registered before this key existed
is an implement variant, so defaulting the other way would refuse a registry
the moment this build shipped. And the failing direction matters more than the
symmetry: answering `groom` for a manifest this reader cannot open would let a
directory fault promote a variant through the groom door, while the completeness
refusal that reports such a fault fires later in
`_dispatcher_workflow_variant`. The one kind that has to be SAID is the one
that unlocks the door.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variants import (
    WorkflowVariant,
    workflow_registry,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "WORKFLOW_KIND_GROOM",
    "WORKFLOW_KIND_IMPLEMENT",
    "WORKFLOW_KIND_INPUT_NAME",
    "declared_workflow_kind",
    "groom_variant_names",
    "is_groom_variant",
    "variant_kind",
]

# The two kinds the ratified cut names. `groom` drafts a decomposition and
# files the approved slices; `implement` is every other variant, including the
# reserved workflow.
WORKFLOW_KIND_GROOM = "groom"
WORKFLOW_KIND_IMPLEMENT = "implement"

# The `[run.inputs]` name a variant declares its kind under.
#
# PUBLIC because the seam-equivalence gate has to classify it. That gate holds
# every declared input to one of the families it knows, and reports any name
# belonging to none as a scoping rot -- which is the right rule and would
# otherwise fire on every groom variant, since this name is the one input a
# variant declares that is NOT a projection of anything. The gate therefore
# reads the name from HERE rather than restating it: a second spelling is
# exactly how the reader of the declaration and the classifier of it would come
# to disagree about which name the kind rides.
WORKFLOW_KIND_INPUT_NAME = "workflow_kind"

# The manifest the name is read from -- the same file
# `_dispatcher_workflow_variant` requires a complete variant directory to hold.
_VARIANT_MANIFEST = "workflow.toml"


def declared_workflow_kind(*, committed_text: str) -> str | None:
    """The kind a committed run config declares, or None when it declares none.

    Reuses the SHARED `[run.inputs]` scan rather than adding a third regex over
    the same table: two copies of that scan is exactly how two callers would
    come to disagree about what one payload declares.

    An empty value reads as no declaration. A run config carrying
    `workflow_kind = ""` has said nothing, and reporting the empty string as a
    kind would push the decision about what silence means out to every caller.
    """
    declared = workflow_declared_inputs(committed_text=committed_text).get(WORKFLOW_KIND_INPUT_NAME)
    if declared is None:
        return None
    stripped = declared.strip()
    return stripped if stripped != "" else None


def variant_kind(*, repo: Path, variant: WorkflowVariant) -> str:
    """The kind of the variant one dispatch selected, defaulting to `implement`.

    The reserved variant answers WITHOUT reading a file. Its `directory` is
    None because the reserved name is never read from the registry, and the
    contract states its kind outright, so there is no manifest to consult and
    no fault that could change the answer.
    """
    if variant.directory is None:
        return WORKFLOW_KIND_IMPLEMENT
    return _directory_kind(repo=repo, directory=variant.directory)


def is_groom_variant(*, repo: Path, variant: WorkflowVariant) -> bool:
    """Whether the selected variant is the groom kind."""
    return variant_kind(repo=repo, variant=variant) == WORKFLOW_KIND_GROOM


def groom_variant_names(*, repo: Path) -> tuple[str, ...]:
    """Every name this repository registers whose directory declares `groom`.

    Sorted, because it is rendered into refusal text: an operator comparing two
    refusals should not have to notice that a set iterated differently.
    """
    registry = workflow_registry(block=dispatcher_block(cwd=repo))
    return tuple(
        sorted(
            name
            for name, directory in registry.items()
            if _directory_kind(repo=repo, directory=directory) == WORKFLOW_KIND_GROOM
        )
    )


def _directory_kind(*, repo: Path, directory: str) -> str:
    manifest = repo / directory / _VARIANT_MANIFEST
    read = attempt(action=lambda: manifest.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return WORKFLOW_KIND_IMPLEMENT
    declared = declared_workflow_kind(committed_text=read)
    return declared if declared is not None else WORKFLOW_KIND_IMPLEMENT
