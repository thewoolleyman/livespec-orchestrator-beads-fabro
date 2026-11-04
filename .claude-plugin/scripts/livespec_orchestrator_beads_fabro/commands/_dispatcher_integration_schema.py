"""The ONE versioned schema of what the orchestrator requires of a governed repo.

`SPECIFICATION/contracts.md`, the repository-integration-contract section,
ratifies that the set of integration points the orchestrator imposes on a governed repository is an
API, and that it is TYPED: every point is a field of one versioned
`RepoIntegrationContract`, and a point that is not a field is not a requirement
the orchestrator may impose. This module is that schema.

THE FIELD SET IS CLOSED. `INTEGRATION_FIELDS` enumerates every ratified
obligation and nothing else -- a NEW dispatch-time or post-merge obligation
requires ratification with its own members-and-adopters disposition before a
field for it may exist here. That is why the enumeration is a literal tuple in
one place rather than a registry assembled from decorators: a reader can see the
whole closed set at once, and adding to it is a diff a reviewer cannot miss.

COMMANDS ARE ARGV, NEVER SHELL STRINGS. Every command-shaped field resolves to a
`tuple[str, ...]` of argv tokens. An adopter still DECLARES its command the way
it always could -- as a shell string that the resolver splits, or as a JSON array
-- because no committed key or its ratified semantics migrate here; what changes
is that nothing downstream ever handles the command as one opaque string again.

VENUE IS A SCHEMA DIMENSION, NOT TWO LITERALS. The check-suite legitimately
differs between the host janitor and the in-sandbox gate, so BOTH venues are
fields, reading the SAME committed declaration and differing only in their fleet
default. Before this, the host argv lived in the janitor resolver and the sandbox
one lived as bare prose in a publish prompt, with nothing binding them -- which
is exactly the "two divergent literals" the clause forbids.

THE DEFAULT BRANCH IS A FIELD WHOSE DECLARATION IS THE REPOSITORY ITSELF. Its
value comes from the ratified default-branch resolution (`origin/HEAD`, then the
forge) rather than from `.livespec.jsonc`, so its lookup path is deliberately not
under a committed block. It is REQUIRED for the same reason `compat.pinned` is:
the only substitutable value would be the `master` literal the clause retires.

WHAT THIS MODULE DELIBERATELY NO LONGER HOLDS. The DESCRIPTOR TYPE every field
below is an instance of lives in `_dispatcher_integration_field`, and the RESOLVED
CONTRACT those fields resolve into lives in `_dispatcher_integration_contract`.
Both were split off by cohesion: this module is read to answer "which obligations
exist", and the other two are read to answer "what may be said about one" and
"what did one repository answer" -- three questions that change on three separate
occasions.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    CONFORMANCE_HOOK_INSTALL_INTERNAL_ARGV,
    CONFORMANCE_MODES,
    CONFORMANCE_NO_OP,
    CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_INTERNAL_ARGV,
    CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_INTERNAL_ARGV,
    FLEET_CORE_REPO_URL,
    JANITOR_BOOTSTRAP_RECIPE_DEFAULT,
    JANITOR_CHECK_SUITE_DEFAULT,
    MASTER_CI_JOB_DEFAULT,
    MASTER_CI_WORKFLOW_DEFAULT,
    MERGE_MODE_DEFAULT,
    MERGE_MODES,
    SANDBOX_CHECK_SUITE_DEFAULT,
    SANDBOX_EXEMPT_MARKER_DEFAULT,
    SANDBOX_EXEMPT_MARKERS,
    TOOLCHAIN_NO_OP,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_field import (
    SHAPE_ARGV,
    SHAPE_CONFORMANCE,
    SHAPE_ENUM,
    SHAPE_NAME,
    VENUE_HOST_JANITOR,
    VENUE_IN_SANDBOX_GATE,
    IntegrationField,
)

__all__: list[str] = [
    "COMPAT_CORE_REPO_KEY",
    "COMPAT_PINNED_KEY",
    "CONFORMANCE_FIELDS",
    "CONFORMANCE_HOOK_INSTALL_FIELD",
    "CONFORMANCE_HOOK_INSTALL_KEY",
    "CONFORMANCE_KEY",
    "CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_FIELD",
    "CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_KEY",
    "CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_FIELD",
    "CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_KEY",
    "CORE_PINNED_REF_FIELD",
    "CORE_REPO_URL_FIELD",
    "DEFAULT_BRANCH_FIELD",
    "DEFAULT_BRANCH_KEY",
    "INTEGRATION_CONTRACT_SCHEMA_VERSION",
    "INTEGRATION_FIELDS",
    "JANITOR_BOOTSTRAP_KEY",
    "JANITOR_BOOTSTRAP_RECIPE_FIELD",
    "JANITOR_BOOTSTRAP_RECIPE_KEY",
    "JANITOR_CHECK_SUITE_FIELD",
    "JANITOR_CHECK_SUITE_KEY",
    "MASTER_CI_JOB_FIELD",
    "MASTER_CI_JOB_KEY",
    "MASTER_CI_KEY",
    "MASTER_CI_WORKFLOW_FIELD",
    "MASTER_CI_WORKFLOW_KEY",
    "MERGE_MODE_FIELD",
    "MERGE_MODE_KEY",
    "PREPARE_TOOLCHAIN_LEFTHOOK_FIELD",
    "PREPARE_TOOLCHAIN_LEFTHOOK_KEY",
    "PREPARE_TOOLCHAIN_MISE_FIELD",
    "PREPARE_TOOLCHAIN_MISE_KEY",
    "PREPARE_TOOLCHAIN_PYTHON_SYNC_FIELD",
    "PREPARE_TOOLCHAIN_PYTHON_SYNC_KEY",
    "SANDBOX_CHECK_SUITE_FIELD",
    "SANDBOX_EXEMPT_MARKER_FIELD",
    "SANDBOX_EXEMPT_MARKER_KEY",
]

# The version the executing plugin build requires of a repository's declaration.
# It is a CONSTANT of the schema rather than a per-field annotation because the
# contract version IS the schema version: a build names one number, and the
# validation pass grades a declaration against that number as a whole.
INTEGRATION_CONTRACT_SCHEMA_VERSION = 1

# The committed keys, spelled EXACTLY as every operator-facing refusal names
# them, so a reader of a refusal knows where in `.livespec.jsonc` to write the
# answer. The `compat` pair is fully qualified because it hangs off the PLUGIN
# block rather than the `dispatcher` block, and a bare `compat.pinned` would send
# an adopter to the wrong nesting level.
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"

MASTER_CI_KEY = "dispatcher.master_ci"
MASTER_CI_WORKFLOW_KEY = f"{MASTER_CI_KEY}.workflow"
MASTER_CI_JOB_KEY = f"{MASTER_CI_KEY}.job"
JANITOR_CHECK_SUITE_KEY = "dispatcher.janitor.check_suite"
JANITOR_BOOTSTRAP_KEY = "dispatcher.janitor_bootstrap"
JANITOR_BOOTSTRAP_RECIPE_KEY = f"{JANITOR_BOOTSTRAP_KEY}.recipe"
COMPAT_PINNED_KEY = f"{_PLUGIN_BLOCK}.compat.pinned"
COMPAT_CORE_REPO_KEY = f"{_PLUGIN_BLOCK}.compat.core_repo"
MERGE_MODE_KEY = "dispatcher.merge_mode"
SANDBOX_EXEMPT_MARKER_KEY = "dispatcher.sandbox_exempt_marker"
PREPARE_TOOLCHAIN_MISE_KEY = "dispatcher.prepare_toolchain.mise"
PREPARE_TOOLCHAIN_LEFTHOOK_KEY = "dispatcher.prepare_toolchain.lefthook"
# The PYTHON DEPENDENCY SYNC premise, named for what it establishes rather than
# for the tool that establishes it: the step populates the sandbox's project
# environment, and every repository reaches that through its own tooling. It was
# a bare constant in the committed run configs until a dispatch of a governed
# repository carrying no `pyproject.toml` died in preparation on it, before any
# agent turn, which is the silent-degrade shape the
# factory-sandbox-toolchain-disposition clause forbids and the shape its two
# neighbours had already been given a premise for.
PREPARE_TOOLCHAIN_PYTHON_SYNC_KEY = "dispatcher.prepare_toolchain.python_sync"

# The three DISPATCH-TIME BASELINE CONFORMANCE premises: installing the
# commit-refuse Mechanism in the sandbox, and the two Verifiers that prove the
# hook and the plugin resolution are actually there. They are declared under
# their own `conformance` block rather than beside the `prepare_toolchain` pair
# because they answer a different question -- those two provision a TOOLCHAIN,
# these three establish a CONFORMANCE PREMISE the ratified baseline gate names.
CONFORMANCE_KEY = "dispatcher.conformance"
CONFORMANCE_HOOK_INSTALL_KEY = f"{CONFORMANCE_KEY}.hook_install"
CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_KEY = f"{CONFORMANCE_KEY}.verify_commit_refuse_hook"
CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_KEY = f"{CONFORMANCE_KEY}.verify_plugin_resolution"

# The default branch is resolved from the repository's own git/forge state, so
# its lookup path sits OUTSIDE every committed block on purpose: nothing an
# adopter writes in `.livespec.jsonc` may answer it.
DEFAULT_BRANCH_KEY = "default_branch"


MASTER_CI_WORKFLOW_FIELD = IntegrationField(
    attribute="master_ci_workflow",
    key=MASTER_CI_WORKFLOW_KEY,
    path=MASTER_CI_WORKFLOW_KEY,
    shape=SHAPE_NAME,
    fleet_default=MASTER_CI_WORKFLOW_DEFAULT,
    parent_key=MASTER_CI_KEY,
)

MASTER_CI_JOB_FIELD = IntegrationField(
    attribute="master_ci_job",
    key=MASTER_CI_JOB_KEY,
    path=MASTER_CI_JOB_KEY,
    shape=SHAPE_NAME,
    fleet_default=MASTER_CI_JOB_DEFAULT,
    parent_key=MASTER_CI_KEY,
)

JANITOR_CHECK_SUITE_FIELD = IntegrationField(
    attribute="janitor_check_suite",
    key=JANITOR_CHECK_SUITE_KEY,
    path=JANITOR_CHECK_SUITE_KEY,
    shape=SHAPE_ARGV,
    fleet_default=JANITOR_CHECK_SUITE_DEFAULT,
    venue=VENUE_HOST_JANITOR,
)

SANDBOX_CHECK_SUITE_FIELD = IntegrationField(
    attribute="sandbox_check_suite",
    key=JANITOR_CHECK_SUITE_KEY,
    path=JANITOR_CHECK_SUITE_KEY,
    shape=SHAPE_ARGV,
    fleet_default=SANDBOX_CHECK_SUITE_DEFAULT,
    venue=VENUE_IN_SANDBOX_GATE,
)

JANITOR_BOOTSTRAP_RECIPE_FIELD = IntegrationField(
    attribute="janitor_bootstrap_recipe",
    key=JANITOR_BOOTSTRAP_RECIPE_KEY,
    path=JANITOR_BOOTSTRAP_RECIPE_KEY,
    shape=SHAPE_ARGV,
    fleet_default=JANITOR_BOOTSTRAP_RECIPE_DEFAULT,
    parent_key=JANITOR_BOOTSTRAP_KEY,
)

CORE_REPO_URL_FIELD = IntegrationField(
    attribute="core_repo_url",
    key=COMPAT_CORE_REPO_KEY,
    path="compat.core_repo",
    shape=SHAPE_NAME,
    fleet_default=FLEET_CORE_REPO_URL,
)

CORE_PINNED_REF_FIELD = IntegrationField(
    attribute="core_pinned_ref",
    key=COMPAT_PINNED_KEY,
    path="compat.pinned",
    shape=SHAPE_NAME,
    required=True,
)

PREPARE_TOOLCHAIN_MISE_FIELD = IntegrationField(
    attribute="prepare_toolchain_mise",
    key=PREPARE_TOOLCHAIN_MISE_KEY,
    path=PREPARE_TOOLCHAIN_MISE_KEY,
    shape=SHAPE_ARGV,
    fleet_default=TOOLCHAIN_NO_OP,
)

PREPARE_TOOLCHAIN_PYTHON_SYNC_FIELD = IntegrationField(
    attribute="prepare_toolchain_python_sync",
    key=PREPARE_TOOLCHAIN_PYTHON_SYNC_KEY,
    path=PREPARE_TOOLCHAIN_PYTHON_SYNC_KEY,
    shape=SHAPE_ARGV,
    fleet_default=TOOLCHAIN_NO_OP,
)

PREPARE_TOOLCHAIN_LEFTHOOK_FIELD = IntegrationField(
    attribute="prepare_toolchain_lefthook",
    key=PREPARE_TOOLCHAIN_LEFTHOOK_KEY,
    path=PREPARE_TOOLCHAIN_LEFTHOOK_KEY,
    shape=SHAPE_ARGV,
    fleet_default=TOOLCHAIN_NO_OP,
)

CONFORMANCE_HOOK_INSTALL_FIELD = IntegrationField(
    attribute="conformance_hook_install",
    key=CONFORMANCE_HOOK_INSTALL_KEY,
    path=CONFORMANCE_HOOK_INSTALL_KEY,
    shape=SHAPE_CONFORMANCE,
    fleet_default=CONFORMANCE_NO_OP,
    admitted=CONFORMANCE_MODES,
    internal_argv=CONFORMANCE_HOOK_INSTALL_INTERNAL_ARGV,
)

CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_FIELD = IntegrationField(
    attribute="conformance_verify_commit_refuse_hook",
    key=CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_KEY,
    path=CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_KEY,
    shape=SHAPE_CONFORMANCE,
    fleet_default=CONFORMANCE_NO_OP,
    admitted=CONFORMANCE_MODES,
    internal_argv=CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_INTERNAL_ARGV,
)

CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_FIELD = IntegrationField(
    attribute="conformance_verify_plugin_resolution",
    key=CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_KEY,
    path=CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_KEY,
    shape=SHAPE_CONFORMANCE,
    fleet_default=CONFORMANCE_NO_OP,
    admitted=CONFORMANCE_MODES,
    internal_argv=CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_INTERNAL_ARGV,
)

# The conformance premises as their own tuple, so a seam asking "is this field a
# conformance premise?" reads the schema rather than matching on an attribute
# name. Deliberately NOT a second closed set: `INTEGRATION_FIELDS` below still
# enumerates every field, and these three are members of it.
CONFORMANCE_FIELDS: tuple[IntegrationField, ...] = (
    CONFORMANCE_HOOK_INSTALL_FIELD,
    CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_FIELD,
    CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_FIELD,
)

DEFAULT_BRANCH_FIELD = IntegrationField(
    attribute="default_branch",
    key=DEFAULT_BRANCH_KEY,
    path=DEFAULT_BRANCH_KEY,
    shape=SHAPE_NAME,
    required=True,
    declared_in_config=False,
)

MERGE_MODE_FIELD = IntegrationField(
    attribute="merge_mode",
    key=MERGE_MODE_KEY,
    path=MERGE_MODE_KEY,
    shape=SHAPE_ENUM,
    fleet_default=MERGE_MODE_DEFAULT,
    admitted=MERGE_MODES,
)

SANDBOX_EXEMPT_MARKER_FIELD = IntegrationField(
    attribute="sandbox_exempt_marker",
    key=SANDBOX_EXEMPT_MARKER_KEY,
    path=SANDBOX_EXEMPT_MARKER_KEY,
    shape=SHAPE_ENUM,
    fleet_default=SANDBOX_EXEMPT_MARKER_DEFAULT,
    admitted=SANDBOX_EXEMPT_MARKERS,
)

# The CLOSED set. Order is the order a validation pass enumerates defects in, so
# it is grouped by family rather than alphabetically: an adopter reading one
# refusal sees its pipeline, then its janitor, then its core, then its sandbox.
INTEGRATION_FIELDS: tuple[IntegrationField, ...] = (
    MASTER_CI_WORKFLOW_FIELD,
    MASTER_CI_JOB_FIELD,
    JANITOR_CHECK_SUITE_FIELD,
    SANDBOX_CHECK_SUITE_FIELD,
    JANITOR_BOOTSTRAP_RECIPE_FIELD,
    CORE_REPO_URL_FIELD,
    CORE_PINNED_REF_FIELD,
    PREPARE_TOOLCHAIN_MISE_FIELD,
    PREPARE_TOOLCHAIN_PYTHON_SYNC_FIELD,
    PREPARE_TOOLCHAIN_LEFTHOOK_FIELD,
    CONFORMANCE_HOOK_INSTALL_FIELD,
    CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_FIELD,
    CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_FIELD,
    DEFAULT_BRANCH_FIELD,
    MERGE_MODE_FIELD,
    SANDBOX_EXEMPT_MARKER_FIELD,
)
