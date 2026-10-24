"""ONE governed repository's WHOLE contract, resolved once and frozen.

The sibling resolver answers ONE point: given a field descriptor and a
declaration, which of `Declared | FleetDefault | Defective` is it. This module
answers the other half of the ratified resolve-once-project-everywhere clause --
the assembly of the CLOSED FIELD SET into a single frozen object every seam then
projects off. The two change for different reasons: a newly admitted value shape
or a change to the three-arm rule is a resolver edit, while a newly ratified
FIELD is an edit here and in the schema and nowhere else.

The direction of the dependency is what keeps that separation honest. This module
imports the schema and the resolver; neither imports it. So the resolver cannot
quietly acquire knowledge of which fields exist, which is exactly the coupling
that would let a second, disagreeing assembly grow somewhere downstream.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_resolver import (
    Defective,
    IntegrationResolution,
    resolve_integration_field,
    resolved_argv,
    resolved_name,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    CONFORMANCE_HOOK_INSTALL_FIELD,
    CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_FIELD,
    CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_FIELD,
    CORE_PINNED_REF_FIELD,
    CORE_REPO_URL_FIELD,
    DEFAULT_BRANCH_FIELD,
    INTEGRATION_CONTRACT_SCHEMA_VERSION,
    INTEGRATION_FIELDS,
    JANITOR_BOOTSTRAP_RECIPE_FIELD,
    JANITOR_CHECK_SUITE_FIELD,
    MASTER_CI_JOB_FIELD,
    MASTER_CI_WORKFLOW_FIELD,
    MERGE_MODE_FIELD,
    PREPARE_TOOLCHAIN_LEFTHOOK_FIELD,
    PREPARE_TOOLCHAIN_MISE_FIELD,
    PREPARE_TOOLCHAIN_PYTHON_SYNC_FIELD,
    SANDBOX_CHECK_SUITE_FIELD,
    SANDBOX_EXEMPT_MARKER_FIELD,
)

__all__: list[str] = [
    "RepoIntegrationContract",
    "ResolvedIntegrationContract",
    "resolve_integration_contract",
]


@dataclass(frozen=True, kw_only=True)
class RepoIntegrationContract:
    """The resolved integration points of ONE governed repository.

    Every field carries the value the generic resolver produced -- declared, or
    the fleet default -- with an unresolvable field carrying its shape's
    sentinel (`UNRESOLVED_NAME`, or the empty argv) rather than a plausible
    fallback. A caller that ignores the accompanying defects therefore fails on
    something that cannot run, never on a fleet value the repository has already
    said is not its own.

    Command-shaped fields are argv tuples, never shell strings: the split
    happens ONCE, here, so no seam downstream re-tokenizes a command and no seam
    can disagree with another about where its arguments end.
    """

    schema_version: int
    master_ci_workflow: str
    master_ci_job: str
    janitor_check_suite: tuple[str, ...]
    sandbox_check_suite: tuple[str, ...]
    janitor_bootstrap_recipe: tuple[str, ...]
    core_repo_url: str
    core_pinned_ref: str
    prepare_toolchain_mise: tuple[str, ...]
    prepare_toolchain_python_sync: tuple[str, ...]
    prepare_toolchain_lefthook: tuple[str, ...]
    conformance_hook_install: tuple[str, ...]
    conformance_verify_commit_refuse_hook: tuple[str, ...]
    conformance_verify_plugin_resolution: tuple[str, ...]
    default_branch: str
    merge_mode: str
    sandbox_exempt_marker: str


@dataclass(frozen=True, kw_only=True)
class ResolvedIntegrationContract:
    """One repository's whole contract, resolved once, with every defect together.

    `defects` carries EVERY unresolved point rather than the first, because the
    ratified validation pass refuses enumerating all of them in one message: an
    adopter that has declared nothing learns the whole list in one refusal
    instead of one dispatch at a time.

    `resolutions` carries the per-field ARM the resolver took, keyed by the
    schema field's attribute. It exists because `contract` carries only VALUES,
    and a value cannot say whether the repository declared it: a repository is
    free to declare exactly the fleet convention, so `Declared` and
    `FleetDefault` can hold identical bytes. A seam whose behaviour turns on
    that distinction -- the host janitor, whose per-invocation `--janitor`
    override is scoped to a repository that declared no check-suite -- would
    otherwise have to re-resolve the field to find out, which is the
    re-derivation the resolve-once rule exists to forbid.
    """

    contract: RepoIntegrationContract
    defects: tuple[Defective, ...]
    resolutions: Mapping[str, IntegrationResolution]


def resolve_integration_contract(
    *, declaration: Mapping[str, object]
) -> ResolvedIntegrationContract:
    """Resolve the WHOLE closed field set once, keeping every defect together.

    This is the "resolve once, project everywhere" object: a seam that needs an
    integration value reads it off the frozen contract instead of re-deriving it
    from configuration, because re-deriving at a later point is how the dispatch
    record and the run come to disagree.
    """
    resolved = {
        field.attribute: resolve_integration_field(field=field, declaration=declaration)
        for field in INTEGRATION_FIELDS
    }
    contract = RepoIntegrationContract(
        schema_version=INTEGRATION_CONTRACT_SCHEMA_VERSION,
        master_ci_workflow=resolved_name(resolution=resolved[MASTER_CI_WORKFLOW_FIELD.attribute]),
        master_ci_job=resolved_name(resolution=resolved[MASTER_CI_JOB_FIELD.attribute]),
        janitor_check_suite=resolved_argv(resolution=resolved[JANITOR_CHECK_SUITE_FIELD.attribute]),
        sandbox_check_suite=resolved_argv(resolution=resolved[SANDBOX_CHECK_SUITE_FIELD.attribute]),
        janitor_bootstrap_recipe=resolved_argv(
            resolution=resolved[JANITOR_BOOTSTRAP_RECIPE_FIELD.attribute]
        ),
        core_repo_url=resolved_name(resolution=resolved[CORE_REPO_URL_FIELD.attribute]),
        core_pinned_ref=resolved_name(resolution=resolved[CORE_PINNED_REF_FIELD.attribute]),
        prepare_toolchain_mise=resolved_argv(
            resolution=resolved[PREPARE_TOOLCHAIN_MISE_FIELD.attribute]
        ),
        prepare_toolchain_python_sync=resolved_argv(
            resolution=resolved[PREPARE_TOOLCHAIN_PYTHON_SYNC_FIELD.attribute]
        ),
        prepare_toolchain_lefthook=resolved_argv(
            resolution=resolved[PREPARE_TOOLCHAIN_LEFTHOOK_FIELD.attribute]
        ),
        conformance_hook_install=resolved_argv(
            resolution=resolved[CONFORMANCE_HOOK_INSTALL_FIELD.attribute]
        ),
        conformance_verify_commit_refuse_hook=resolved_argv(
            resolution=resolved[CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_FIELD.attribute]
        ),
        conformance_verify_plugin_resolution=resolved_argv(
            resolution=resolved[CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_FIELD.attribute]
        ),
        default_branch=resolved_name(resolution=resolved[DEFAULT_BRANCH_FIELD.attribute]),
        merge_mode=resolved_name(resolution=resolved[MERGE_MODE_FIELD.attribute]),
        sandbox_exempt_marker=resolved_name(
            resolution=resolved[SANDBOX_EXEMPT_MARKER_FIELD.attribute]
        ),
    )
    defects = tuple(
        resolution for resolution in resolved.values() if isinstance(resolution, Defective)
    )
    return ResolvedIntegrationContract(
        contract=contract, defects=defects, resolutions=MappingProxyType(resolved)
    )
