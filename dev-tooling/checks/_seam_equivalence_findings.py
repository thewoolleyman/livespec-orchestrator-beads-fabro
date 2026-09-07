# pyright: reportMissingImports=none, reportMissingTypeStubs=none
"""_seam_equivalence_findings — what a disagreement between the surfaces IS, and its name.

The comparison half of `seam_equivalence`. It owns the four input FAMILIES the
`[run.inputs]` table carries, and the four ways those inputs can fail to say one
thing: a position the engine will not render, either direction of the
token/rendered-input equality, a scoping rot, and a schema-leg mismatch. It is
deliberately free of filesystem and reporting concerns -- every function here
takes sets and returns findings -- so the rules can be read and tested without a
payload on disk.

FOUR DISJOINT FAMILIES, AND ONLY THE EQUALITY IS SCOPED TO ONE OF THEM. The
`[run.inputs]` table carries the integration inputs, the six ACP adapter inputs,
the PER-ITEM POLICY inputs -- `review_fix_visit_cap`,
`merge_on_review_cap_outcome` and `merge_hold` -- and the variant's own KIND
DECLARATION. The ratified typed-workflow-inputs clause names the first three and
draws the line between them exactly once: the token/rendered-input EQUALITY
ranges over the integration inputs alone, because only those are projections of
the `ResolvedIntegrationContract`, while the RESOLVED-POSITION rule binds every
declared input whatever family it is in. A policy token in a `timeout` would
leave the node with no timeout and report nothing, exactly as an integration one
would; the engine does not know which family a name belongs to.

WHY THE KIND DECLARATION IS A FAMILY OF ITS OWN rather than folded into one of
the other three. It is the one declared input that projects NOTHING: the
integration inputs are fields of a resolved contract, the adapter inputs name a
node, the policy inputs carry an item's effective policy, and this one is the
variant's statement about ITSELF -- what kind of work its graph does, read back
off this very table by `_workflow_variant_kind`. Folding it into the policy
family would be worse than untidy: that family's declaration leg requires EVERY
payload to declare EVERY name in it, and the reserved workflow deliberately
declares no kind, because its kind is stated by the contract and answered
without reading a file. So the kind is classified, and NOT required.

The scoping is checked rather than assumed: the four name sets must be pairwise
disjoint, and every input the payload declares must fall in one of them, so an
input added tomorrow cannot be silently dropped out of every comparison by
belonging to nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import combinations

# NO `sys.path` bootstrap here, deliberately. This is a PRIVATE module of
# `seam_equivalence`, imported only through it, and that owner already puts this
# directory and the orchestrator package's root on the path before importing
# this file. A second copy of the bootstrap would be dead code that no caller
# can reach and no test can exercise.
from _seam_equivalence_scan import Occurrence
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import NODE_INPUT_CANDIDATES
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    CONTRACT_INPUT_NAMES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    INTEGRATION_FIELDS,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_INPUT_NAME,
)

__all__: list[str] = [
    "ADAPTER_INPUT_NAMES",
    "POLICY_INPUT_NAMES",
    "SCHEMA_PROJECTABLE_INPUTS",
    "VARIANT_KIND_INPUT_NAMES",
    "Finding",
    "classified_input_names",
    "equivalence_findings",
    "non_rendered_occurrences",
    "policy_declaration_findings",
    "position_findings",
    "referenced_integration_inputs",
    "schema_findings",
    "scoping_findings",
]

# The schema's PROJECTABLE fields, named by the workflow input each crosses as.
# Read off the projection's own closed mapping rather than restated, so this
# check cannot come to disagree with the thing it is comparing.
SCHEMA_PROJECTABLE_INPUTS: frozenset[str] = frozenset(CONTRACT_INPUT_NAMES.values())

# The per-node ACP adapter inputs, likewise read off their owning module.
ADAPTER_INPUT_NAMES: frozenset[str] = frozenset(
    name for candidates in NODE_INPUT_CANDIDATES.values() for name in candidates
)

# The PER-ITEM POLICY inputs. Named here rather than read off an owning module
# because they are the one family with no object behind them: the Dispatcher
# renders each from the item's own effective policy -- two cap-shaped settings
# and the merge hold, which is not a setting at all and has no repository-level
# default -- so there is nothing to import them from.
POLICY_INPUT_NAMES: frozenset[str] = frozenset(
    {"review_fix_visit_cap", "merge_on_review_cap_outcome", "merge_hold"}
)

# The variant's own KIND declaration, read off the module that reads it from
# the payload rather than respelled here. That module is the one place that
# decides which `[run.inputs]` name carries a variant's kind, and a second
# spelling in this gate would let the reader and the classifier drift apart --
# after which every groom variant would earn an `unclassified-declared-input`
# finding for the one input it is REQUIRED to declare.
VARIANT_KIND_INPUT_NAMES: frozenset[str] = frozenset({WORKFLOW_KIND_INPUT_NAME})


def classified_input_names() -> frozenset[str]:
    """Every name the four families cover, unioned AT CALL TIME.

    Read live rather than frozen into a module constant so the four families
    stay the single source of the classification: a test that substitutes one
    family, and any future change that computes one of them, cannot leave a
    stale union behind for a second caller to read.
    """
    return (
        SCHEMA_PROJECTABLE_INPUTS
        | ADAPTER_INPUT_NAMES
        | POLICY_INPUT_NAMES
        | VARIANT_KIND_INPUT_NAMES
    )


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One way the three integration-input surfaces fail to say the same thing."""

    kind: str
    detail: str
    subject: str


def referenced_integration_inputs(*, occurrences: Iterable[Occurrence]) -> frozenset[str]:
    """The INTEGRATION inputs the payload references, whatever else it also carries."""
    return frozenset(
        occurrence.name
        for occurrence in occurrences
        if occurrence.name in SCHEMA_PROJECTABLE_INPUTS
    )


def non_rendered_occurrences(*, occurrences: Iterable[Occurrence]) -> list[Occurrence]:
    """Every CLASSIFIED token sitting where the pinned engine would not expand it.

    All four families, not just the integration one: the resolved-position rule
    is about what the ENGINE does with a position, and the engine has never
    known which family a name belongs to. A policy or adapter token in a typed
    attribute leaves the node with no value and reports nothing, which is the
    same silent failure the rule exists to catch.

    An UNCLASSIFIED name is out of scope here, deliberately, and it is not a
    hole: an input belonging to no family is reported by `scoping_findings` as
    the scoping rot it is, which is a more useful finding than a position
    complaint about a name nobody has placed.

    Separate from the finding it produces so the matcher control can assert the
    two agree: a predicate that silently stopped selecting would otherwise take
    the finding with it, and the control would confirm the silence.
    """
    classified = classified_input_names()
    return [
        occurrence
        for occurrence in occurrences
        if occurrence.name in classified and not occurrence.rendered
    ]


def position_findings(*, occurrences: Iterable[Occurrence]) -> list[Finding]:
    """Every classified token the pinned engine would not expand where it sits."""
    return [
        Finding(
            kind="non-rendered-position",
            subject=occurrence.name,
            detail=(
                f"`inputs.{occurrence.name}` sits at {occurrence.venue} "
                f"`{occurrence.position}`, which the pinned engine does not render"
            ),
        )
        for occurrence in non_rendered_occurrences(occurrences=occurrences)
    ]


def equivalence_findings(*, referenced: frozenset[str], rendered: frozenset[str]) -> list[Finding]:
    """The two directions of the equality, each reported by name."""
    findings = [
        Finding(
            kind="token-without-rendered-input",
            subject=name,
            detail=(
                f"the workflow references `inputs.{name}` but the Dispatcher renders no "
                "such input from the resolved integration contract"
            ),
        )
        for name in sorted(referenced - rendered)
    ]
    findings.extend(
        Finding(
            kind="rendered-input-without-token",
            subject=name,
            detail=(
                f"the Dispatcher renders `{name}` from the resolved integration contract "
                "but no workflow position references it"
            ),
        )
        for name in sorted(rendered - referenced)
    )
    return findings


def scoping_findings(*, declared: Mapping[str, str]) -> list[Finding]:
    """That the equality is scoped to the integration subset, and to all of it.

    Two ways the scoping can rot, both silent: a name could belong to two
    families at once, which would make the exclusion ambiguous; or a newly
    declared input could belong to none, which would drop it out of every
    comparison while the payload happily sends it.
    """
    families = (
        ("schema-projectable", SCHEMA_PROJECTABLE_INPUTS),
        ("acp-adapter", ADAPTER_INPUT_NAMES),
        ("per-item-policy", POLICY_INPUT_NAMES),
        ("variant-kind", VARIANT_KIND_INPUT_NAMES),
    )
    findings = [
        Finding(
            kind="overlapping-input-families",
            subject=name,
            detail=f"`{name}` is both {left} and {right}, so the exclusion is ambiguous",
        )
        for (left, left_names), (right, right_names) in combinations(families, 2)
        for name in sorted(left_names & right_names)
    ]
    classified = classified_input_names()
    findings.extend(
        Finding(
            kind="unclassified-declared-input",
            subject=name,
            detail=(
                f"`{name}` is declared by the payload but is none of an integration field, "
                "an ACP adapter, a per-item policy input, or the variant kind declaration"
            ),
        )
        for name in sorted(set(declared) - classified)
    )
    return findings


def policy_declaration_findings(*, declared: Mapping[str, str]) -> list[Finding]:
    """That THIS payload declares every per-item policy input, the bundle's set entire.

    The integration inputs are INTERSECTED with what a payload declares, so a
    payload carrying fewer of them is simply sent fewer. The per-item policy
    inputs are not: the Dispatcher renders all three on every dispatch, because
    they project the ITEM's effective policy rather than the repository's
    contract, and fabro REJECTS an `--input` naming an input the run config does
    not declare. So a payload missing one does not merely disagree with the
    bundle -- every dispatch through it dies before a node runs.

    This is what holds a registered VARIANT to the bundle's token set for the
    family the equality cannot speak about, and it is why the ratified merge
    hold requires the bundle and every variant to declare it.
    """
    return [
        Finding(
            kind="undeclared-policy-input",
            subject=name,
            detail=(
                f"`{name}` is a per-item policy input the Dispatcher renders on EVERY "
                "dispatch, but this payload's `[run.inputs]` table does not declare it, "
                "so fabro would reject the run"
            ),
        )
        for name in sorted(POLICY_INPUT_NAMES - set(declared))
    ]


def schema_findings() -> list[Finding]:
    """That the rendered names and the schema's projectable fields are one vocabulary.

    Both directions, and neither is book-keeping. A projected name that is no
    schema field would mean the Dispatcher renders a point the closed field set
    does not carry. A projected name that DIFFERS from the field it is keyed by
    would be worse and quieter: the equality above compares a set of workflow
    tokens against a set of rendered input names, so the two are only the same
    question while the input name and the schema attribute are the same word --
    which is exactly what the projection's own mapping undertakes to keep.
    """
    schema_attributes = {field.attribute for field in INTEGRATION_FIELDS}
    findings = [
        Finding(
            kind="projection-names-no-schema-field",
            subject=attribute,
            detail=f"the projection names `{attribute}`, which is no field of the schema",
        )
        for attribute in sorted(set(CONTRACT_INPUT_NAMES) - schema_attributes)
    ]
    findings.extend(
        Finding(
            kind="projected-name-differs-from-field",
            subject=name,
            detail=(
                f"schema field `{attribute}` crosses as input `{name}`; the two must be the "
                "same word for a token set and a rendered-input set to be comparable at all"
            ),
        )
        for attribute, name in sorted(CONTRACT_INPUT_NAMES.items())
        if attribute != name
    )
    return findings
