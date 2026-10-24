"""The typed repository-integration contract: one schema, one generic resolver.

`SPECIFICATION/contracts.md`, the repository-integration-contract section,
ratifies that every integration point the orchestrator requires of a governed repository be a
field of one versioned `RepoIntegrationContract`, and that every point be read
through ONE generic resolver returning `Declared | FleetDefault | Defective`.
These tests pin the three arms of that resolver against the schema's own field
descriptors -- including the two arms a per-key default table cannot express: a
REQUIRED field whose absence refuses rather than substituting a value, and a
declared parent block that makes its own halves required.

Every case reaches its module through `_module()`, which asserts the module FILE
exists before importing it, so a slice that has not landed yet fails on a genuine
assertion rather than on an unimportable module. There are five: the CLOSED FIELD
SET, the DESCRIPTOR TYPE its members are instances of, the fleet DEFAULTS they
resolve to, the DECLARATION reader, and the RESOLVER plus the CONTRACT assembly
that reads a whole repository through it.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from types import ModuleType

_COMMANDS = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_DEFAULTS_PATH = _COMMANDS / "_dispatcher_integration_defaults.py"
_SCHEMA_PATH = _COMMANDS / "_dispatcher_integration_schema.py"
_DECLARATION_PATH = _COMMANDS / "_dispatcher_integration_declaration.py"
_RESOLVER_PATH = _COMMANDS / "_dispatcher_integration_resolver.py"
_FIELD_PATH = _COMMANDS / "_dispatcher_integration_field.py"
_CONTRACT_PATH = _COMMANDS / "_dispatcher_integration_contract.py"


def _module(*, path: Path, name: str) -> ModuleType:
    assert path.is_file()
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _defaults() -> ModuleType:
    return _module(path=_DEFAULTS_PATH, name="_dispatcher_integration_defaults")


def _schema() -> ModuleType:
    return _module(path=_SCHEMA_PATH, name="_dispatcher_integration_schema")


def _declaration() -> ModuleType:
    return _module(path=_DECLARATION_PATH, name="_dispatcher_integration_declaration")


def _resolver() -> ModuleType:
    return _module(path=_RESOLVER_PATH, name="_dispatcher_integration_resolver")


def _field_type() -> ModuleType:
    return _module(path=_FIELD_PATH, name="_dispatcher_integration_field")


def _contract() -> ModuleType:
    return _module(path=_CONTRACT_PATH, name="_dispatcher_integration_contract")


def test_the_schema_is_versioned_and_its_contract_dataclass_is_keyword_only() -> None:
    """One versioned schema: an explicit version constant and a kw_only contract."""
    schema = _schema()
    assert isinstance(schema.INTEGRATION_CONTRACT_SCHEMA_VERSION, int)
    contract_type = _contract().RepoIntegrationContract
    assert contract_type.__dataclass_params__.frozen is True
    parameters = list(inspect.signature(contract_type).parameters.values())
    assert parameters
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in parameters)


def test_the_contract_enumerates_every_ratified_integration_point() -> None:
    """The closed field set: check-suite per venue, recipe, pipeline, core, premises, branch."""
    schema = _schema()
    attributes = {field.attribute for field in schema.INTEGRATION_FIELDS}
    assert attributes == {
        "master_ci_workflow",
        "master_ci_job",
        "janitor_check_suite",
        "sandbox_check_suite",
        "janitor_bootstrap_recipe",
        "core_repo_url",
        "core_pinned_ref",
        "prepare_toolchain_mise",
        "prepare_toolchain_python_sync",
        "prepare_toolchain_lefthook",
        "conformance_hook_install",
        "conformance_verify_commit_refuse_hook",
        "conformance_verify_plugin_resolution",
        "default_branch",
        "merge_mode",
        "sandbox_exempt_marker",
    }
    annotations = _contract().RepoIntegrationContract.__annotations__
    assert set(annotations) == attributes | {"schema_version"}


def test_every_command_shaped_field_is_typed_as_argv_tokens_not_a_shell_string() -> None:
    """Commands are argv arrays: the split happens once, in the schema's own type."""
    schema = _schema()
    annotations = _contract().RepoIntegrationContract.__annotations__
    command_shaped = [
        field for field in schema.INTEGRATION_FIELDS if field.shape == _field_type().SHAPE_ARGV
    ]
    assert command_shaped
    for field in command_shaped:
        assert annotations[field.attribute] == "tuple[str, ...]"


def test_the_check_suite_carries_venue_as_an_explicit_schema_dimension() -> None:
    """One declaration, two venues -- never two divergent literals."""
    schema = _schema()
    by_attribute = {field.attribute: field for field in schema.INTEGRATION_FIELDS}
    host = by_attribute["janitor_check_suite"]
    sandbox = by_attribute["sandbox_check_suite"]
    assert host.venue == _field_type().VENUE_HOST_JANITOR
    assert sandbox.venue == _field_type().VENUE_IN_SANDBOX_GATE
    assert host.path == sandbox.path == schema.JANITOR_CHECK_SUITE_KEY
    assert host.fleet_default != sandbox.fleet_default


def test_every_fleet_default_the_resolver_returns_comes_from_the_defaults_module() -> None:
    """One module holds every fleet default, so an adopter-visible value is one diff."""
    defaults = _defaults()
    schema = _schema()
    declared_defaults = {
        field.fleet_default for field in schema.INTEGRATION_FIELDS if not field.required
    }
    module_values = set(vars(defaults)[name] for name in defaults.__all__)
    assert declared_defaults <= module_values


def test_the_toolchain_no_op_arm_is_an_explicit_fleet_default_value() -> None:
    """The no-op is a VALUE a field resolves to, never an absent key inferred from silence."""
    defaults = _defaults()
    schema = _schema()
    resolution = _resolver().resolve_integration_field(
        field=schema.PREPARE_TOOLCHAIN_MISE_FIELD, declaration={}
    )
    assert isinstance(resolution, _resolver().FleetDefault)
    assert resolution.value == defaults.TOOLCHAIN_NO_OP
    lefthook = _resolver().resolve_integration_field(
        field=schema.PREPARE_TOOLCHAIN_LEFTHOOK_FIELD, declaration={}
    )
    assert lefthook.value == defaults.TOOLCHAIN_NO_OP
    # The PYTHON-SYNC premise is named here beside its two neighbours rather
    # than left to the closed-set case above, because the no-op arm is the one
    # this premise exists for: it was a bare constant until bd-ib-xti6q, and a
    # case naming only the other two could not return a hit for the arm that
    # keeps a repository declaring nothing from running a sync at all.
    python_sync = _resolver().resolve_integration_field(
        field=schema.PREPARE_TOOLCHAIN_PYTHON_SYNC_FIELD, declaration={}
    )
    assert python_sync.value == defaults.TOOLCHAIN_NO_OP


def _conformance(*, premise: str, value: object) -> dict[str, object]:
    """A declaration writing ONE conformance premise, nested exactly as the key reads."""
    return {"dispatcher": {"conformance": {premise: value}}}


def test_the_three_conformance_premises_are_declared_under_their_own_keys() -> None:
    """Each prepare-step premise is its own committed key, spelled as a refusal quotes it."""
    schema = _schema()
    keys = {field.attribute: field.key for field in schema.CONFORMANCE_FIELDS}
    assert keys == {
        "conformance_hook_install": "dispatcher.conformance.hook_install",
        "conformance_verify_commit_refuse_hook": (
            "dispatcher.conformance.verify_commit_refuse_hook"
        ),
        "conformance_verify_plugin_resolution": ("dispatcher.conformance.verify_plugin_resolution"),
    }
    # Every one is a member of the closed field set, not a second set beside it.
    assert set(schema.CONFORMANCE_FIELDS) <= set(schema.INTEGRATION_FIELDS)
    for field in schema.CONFORMANCE_FIELDS:
        assert field.shape == _field_type().SHAPE_CONFORMANCE
        assert field.admitted == _defaults().CONFORMANCE_MODES


def test_the_conformance_mode_enumeration_is_closed_and_self_describing() -> None:
    """Three modes, each NAMING what it is rather than ranking a tier or a level."""
    defaults = _defaults()
    assert defaults.CONFORMANCE_MODES == (
        "no_op",
        "shell_argv",
        "internal_livespec_dev_tooling",
    )


def test_an_absent_conformance_premise_resolves_to_the_fleet_default_no_op() -> None:
    """Absence is what the dispatch-time warning fires on -- and it runs nothing."""
    resolver = _resolver()
    defaults = _defaults()
    for field in _schema().CONFORMANCE_FIELDS:
        resolution = _resolver().resolve_integration_field(field=field, declaration={})
        assert isinstance(resolution, resolver.FleetDefault)
        assert resolution.value == defaults.CONFORMANCE_NO_OP


def test_an_explicit_no_op_resolves_to_declared_carrying_the_same_empty_argv() -> None:
    """The adopter CHOSE the skip, so the arm differs even though the value cannot."""
    resolver = _resolver()
    schema = _schema()
    resolution = _resolver().resolve_integration_field(
        field=schema.CONFORMANCE_HOOK_INSTALL_FIELD,
        declaration=_conformance(premise="hook_install", value={"mode": "no_op"}),
    )
    assert isinstance(resolution, resolver.Declared)
    assert resolution.value == _defaults().CONFORMANCE_NO_OP


def test_a_shell_argv_conformance_premise_carries_the_adopters_command_verbatim() -> None:
    """The sandbox runs what the adopter wrote, as an argv array or as a shell string."""
    resolver = _resolver()
    schema = _schema()
    declared = _resolver().resolve_integration_field(
        field=schema.CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_FIELD,
        declaration=_conformance(
            premise="verify_plugin_resolution",
            value={"mode": "shell_argv", "argv": ["make", "verify plugins"]},
        ),
    )
    assert isinstance(declared, resolver.Declared)
    assert declared.value == ("make", "verify plugins")


def test_a_shell_argv_premise_without_a_usable_argv_is_defective_naming_the_key() -> None:
    """Declaring a command and then naming none resolves nothing; it never falls back."""
    resolver = _resolver()
    schema = _schema()
    for argv in (None, [], "", ["", "check"]):
        value: dict[str, object] = {"mode": "shell_argv"}
        if argv is not None:
            value["argv"] = argv
        resolution = _resolver().resolve_integration_field(
            field=schema.CONFORMANCE_HOOK_INSTALL_FIELD,
            declaration=_conformance(premise="hook_install", value=value),
        )
        assert isinstance(resolution, resolver.Defective)
        assert resolution.key == schema.CONFORMANCE_HOOK_INSTALL_KEY


def test_the_internal_mode_renders_the_invocation_the_defaults_module_holds() -> None:
    """The one place a fleet invocation may be spelled is the fleet-defaults module."""
    resolver = _resolver()
    schema = _schema()
    defaults = _defaults()
    expected = {
        schema.CONFORMANCE_HOOK_INSTALL_FIELD: defaults.CONFORMANCE_HOOK_INSTALL_INTERNAL_ARGV,
        schema.CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_FIELD: (
            defaults.CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_INTERNAL_ARGV
        ),
        schema.CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_FIELD: (
            defaults.CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_INTERNAL_ARGV
        ),
    }
    for field, argv in expected.items():
        premise = field.key.rsplit(".", 1)[-1]
        resolution = _resolver().resolve_integration_field(
            field=field,
            declaration=_conformance(
                premise=premise, value={"mode": "internal_livespec_dev_tooling"}
            ),
        )
        assert isinstance(resolution, resolver.Declared)
        assert resolution.value == argv
        assert field.internal_argv == argv


def test_a_conformance_premise_outside_the_closed_enumeration_is_defective() -> None:
    """A mode nobody ratified, or a value that is no mapping at all, resolves nothing."""
    resolver = _resolver()
    schema = _schema()
    for value in ("no_op", 7, None, {}, {"mode": "tier_two"}, {"mode": 3}):
        resolution = _resolver().resolve_integration_field(
            field=schema.CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_FIELD,
            declaration=_conformance(premise="verify_commit_refuse_hook", value=value),
        )
        assert isinstance(resolution, resolver.Defective)
        assert resolution.key == schema.CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_KEY
        for mode in _defaults().CONFORMANCE_MODES:
            assert f"`{mode}`" in resolution.reason


def test_a_mode_that_takes_no_argv_refuses_a_declaration_that_supplies_one() -> None:
    """A premise cannot both name a fleet invocation and hand one of its own."""
    resolver = _resolver()
    schema = _schema()
    for mode in ("no_op", "internal_livespec_dev_tooling"):
        resolution = _resolver().resolve_integration_field(
            field=schema.CONFORMANCE_HOOK_INSTALL_FIELD,
            declaration=_conformance(
                premise="hook_install", value={"mode": mode, "argv": ["make", "hooks"]}
            ),
        )
        assert isinstance(resolution, resolver.Defective)
        assert resolution.key == schema.CONFORMANCE_HOOK_INSTALL_KEY
        assert "argv" in resolution.reason


def test_the_schema_version_constant_is_unchanged_by_the_conformance_fields() -> None:
    """These fields complete a field set the ratified version already assumed."""
    assert _schema().INTEGRATION_CONTRACT_SCHEMA_VERSION == 1


def test_a_declared_usable_key_resolves_to_declared() -> None:
    """The repository answered, and the answer is usable."""
    resolver = _resolver()
    schema = _schema()
    declaration: dict[str, object] = {
        "dispatcher": {"janitor": {"check_suite": "make ci --verbose"}}
    }
    resolution = _resolver().resolve_integration_field(
        field=schema.JANITOR_CHECK_SUITE_FIELD, declaration=declaration
    )
    assert isinstance(resolution, resolver.Declared)
    assert resolution.value == ("make", "ci", "--verbose")
    assert resolver.is_declared(resolution=resolution) is True


def test_a_command_declared_as_an_argv_array_resolves_to_the_same_tokens() -> None:
    """Argv is the typed form, so declaring one directly is honored verbatim."""
    resolver = _resolver()
    schema = _schema()
    declaration: dict[str, object] = {
        "dispatcher": {"janitor": {"check_suite": ["make", "ci --verbose"]}}
    }
    resolution = _resolver().resolve_integration_field(
        field=schema.JANITOR_CHECK_SUITE_FIELD, declaration=declaration
    )
    assert isinstance(resolution, resolver.Declared)
    assert resolution.value == ("make", "ci --verbose")


def test_only_an_absent_optional_key_with_a_declared_default_resolves_to_fleet_default() -> None:
    """An absent key is an ANSWER: this repository uses the fleet convention."""
    resolver = _resolver()
    schema = _schema()
    defaults = _defaults()
    resolution = _resolver().resolve_integration_field(
        field=schema.JANITOR_CHECK_SUITE_FIELD, declaration={}
    )
    assert isinstance(resolution, resolver.FleetDefault)
    assert resolution.value == defaults.JANITOR_CHECK_SUITE_DEFAULT
    assert resolver.is_declared(resolution=resolution) is False
    present_parent: dict[str, object] = {"dispatcher": {"janitor": {}}}
    assert isinstance(
        _resolver().resolve_integration_field(
            field=schema.JANITOR_CHECK_SUITE_FIELD, declaration=present_parent
        ),
        resolver.FleetDefault,
    )


def test_an_absent_required_key_with_no_default_resolves_to_defective_naming_it() -> None:
    """`compat.pinned` refuses on absence rather than substituting a moving branch tip."""
    resolver = _resolver()
    schema = _schema()
    resolution = _resolver().resolve_integration_field(
        field=schema.CORE_PINNED_REF_FIELD, declaration={}
    )
    assert isinstance(resolution, resolver.Defective)
    assert resolution.key == schema.COMPAT_PINNED_KEY
    assert schema.COMPAT_PINNED_KEY in resolution.reason
    assert "master" not in resolution.reason
    assert resolver.resolved_name(resolution=resolution) == _defaults().UNRESOLVED_NAME


def test_the_default_branch_is_required_and_never_completed_from_a_literal() -> None:
    """A branch nobody could name is a defect, not a `master` the adopter never chose."""
    resolver = _resolver()
    schema = _schema()
    absent = _resolver().resolve_integration_field(
        field=schema.DEFAULT_BRANCH_FIELD, declaration={}
    )
    assert isinstance(absent, resolver.Defective)
    declared = _resolver().resolve_integration_field(
        field=schema.DEFAULT_BRANCH_FIELD, declaration={"default_branch": "main"}
    )
    assert isinstance(declared, resolver.Declared)
    assert declared.value == "main"


def test_a_present_but_unusable_key_resolves_to_defective_naming_key_and_reason() -> None:
    """A present declaration is never completed from the convention it contradicts."""
    resolver = _resolver()
    schema = _schema()
    for raw in (None, "", "   ", 7):
        resolution = _resolver().resolve_integration_field(
            field=schema.CORE_REPO_URL_FIELD, declaration={"compat": {"core_repo": raw}}
        )
        assert isinstance(resolution, resolver.Defective)
        assert resolution.key == schema.COMPAT_CORE_REPO_KEY
        assert "non-empty string" in resolution.reason


def test_an_unparseable_or_programless_command_resolves_to_defective() -> None:
    """A command that names no program resolves nothing; it never falls back."""
    resolver = _resolver()
    schema = _schema()
    for raw in ('just "unbalanced', "", "''", [], ["", "check"], [1], 7):
        declaration: dict[str, object] = {"dispatcher": {"janitor": {"check_suite": raw}}}
        resolution = _resolver().resolve_integration_field(
            field=schema.JANITOR_CHECK_SUITE_FIELD, declaration=declaration
        )
        assert isinstance(resolution, resolver.Defective)
        assert resolution.key == schema.JANITOR_CHECK_SUITE_KEY
        assert resolver.resolved_argv(resolution=resolution) == _defaults().UNRESOLVED_ARGV


def test_a_declared_parent_block_makes_each_half_of_its_point_required() -> None:
    """Defaulting the missing half would act on a pipeline the repository never named."""
    resolver = _resolver()
    schema = _schema()
    declaration: dict[str, object] = {"dispatcher": {"master_ci": {"workflow": "Build"}}}
    workflow = _resolver().resolve_integration_field(
        field=schema.MASTER_CI_WORKFLOW_FIELD, declaration=declaration
    )
    assert isinstance(workflow, resolver.Declared)
    job = _resolver().resolve_integration_field(
        field=schema.MASTER_CI_JOB_FIELD, declaration=declaration
    )
    assert isinstance(job, resolver.Defective)
    assert schema.MASTER_CI_KEY in job.reason


def test_a_parent_block_that_is_not_a_mapping_blocks_every_field_under_it() -> None:
    """The repository wrote something there, and it is not something a key hangs off."""
    resolver = _resolver()
    schema = _schema()
    declaration: dict[str, object] = {"dispatcher": {"master_ci": "CI"}}
    resolution = _resolver().resolve_integration_field(
        field=schema.MASTER_CI_WORKFLOW_FIELD, declaration=declaration
    )
    assert isinstance(resolution, resolver.Defective)
    assert "is not a mapping" in resolution.reason


def test_merge_mode_admits_a_closed_enum_and_defaults_to_rebase() -> None:
    """The post-merge merge strategy is a declared point with a closed value space."""
    resolver = _resolver()
    schema = _schema()
    defaults = _defaults()
    assert set(schema.MERGE_MODE_FIELD.admitted) == {"rebase", "squash"}
    assert (
        _resolver().resolve_integration_field(field=schema.MERGE_MODE_FIELD, declaration={}).value
        == defaults.MERGE_MODE_DEFAULT
    )
    squash: dict[str, object] = {"dispatcher": {"merge_mode": "squash"}}
    assert (
        _resolver()
        .resolve_integration_field(field=schema.MERGE_MODE_FIELD, declaration=squash)
        .value
        == "squash"
    )
    unsupported: dict[str, object] = {"dispatcher": {"merge_mode": "merge"}}
    defect = _resolver().resolve_integration_field(
        field=schema.MERGE_MODE_FIELD, declaration=unsupported
    )
    assert isinstance(defect, resolver.Defective)
    assert defect.key == schema.MERGE_MODE_KEY


def test_the_sandbox_exempt_marker_is_closed_to_the_one_fleet_value() -> None:
    """A divergent marker key would be set by the projection and honored by no hook."""
    resolver = _resolver()
    schema = _schema()
    defaults = _defaults()
    assert schema.SANDBOX_EXEMPT_MARKER_FIELD.admitted == ("livespec.sandboxExempt",)
    absent = _resolver().resolve_integration_field(
        field=schema.SANDBOX_EXEMPT_MARKER_FIELD, declaration={}
    )
    assert isinstance(absent, resolver.FleetDefault)
    assert absent.value == defaults.SANDBOX_EXEMPT_MARKER_DEFAULT
    other: dict[str, object] = {"dispatcher": {"sandbox_exempt_marker": "acme.sandbox"}}
    assert isinstance(
        _resolver().resolve_integration_field(
            field=schema.SANDBOX_EXEMPT_MARKER_FIELD, declaration=other
        ),
        resolver.Defective,
    )


def test_an_optional_field_missing_its_schema_default_resolves_to_the_sentinel() -> None:
    """A schema bug never leaks None into a value position a caller would run."""
    resolver = _resolver()
    broken = _field_type().IntegrationField(
        attribute="broken",
        key="dispatcher.broken",
        path="dispatcher.broken",
        shape=_field_type().SHAPE_NAME,
    )
    resolution = _resolver().resolve_integration_field(field=broken, declaration={})
    assert isinstance(resolution, resolver.FleetDefault)
    assert resolution.value == _defaults().UNRESOLVED_NAME


def test_the_whole_contract_resolves_once_carrying_every_defect_together() -> None:
    """The validation pass enumerates EVERY unresolved point, not the first."""
    schema = _schema()
    defaults = _defaults()
    resolved = _contract().resolve_integration_contract(declaration={})
    assert resolved.contract.schema_version == schema.INTEGRATION_CONTRACT_SCHEMA_VERSION
    assert resolved.contract.janitor_check_suite == defaults.JANITOR_CHECK_SUITE_DEFAULT
    assert resolved.contract.sandbox_check_suite == defaults.SANDBOX_CHECK_SUITE_DEFAULT
    assert resolved.contract.master_ci_workflow == defaults.MASTER_CI_WORKFLOW_DEFAULT
    assert resolved.contract.core_repo_url == defaults.FLEET_CORE_REPO_URL
    assert resolved.contract.core_pinned_ref == defaults.UNRESOLVED_NAME
    assert resolved.contract.default_branch == defaults.UNRESOLVED_NAME
    assert resolved.contract.merge_mode == defaults.MERGE_MODE_DEFAULT
    assert resolved.contract.sandbox_exempt_marker == defaults.SANDBOX_EXEMPT_MARKER_DEFAULT
    assert {defect.key for defect in resolved.defects} == {
        schema.COMPAT_PINNED_KEY,
        schema.DEFAULT_BRANCH_KEY,
    }


def test_a_fully_declared_repository_resolves_with_no_defects() -> None:
    """Every point answered by the repository, and nothing left for the fleet to supply."""
    declaration: dict[str, object] = {
        "default_branch": "main",
        "compat": {"pinned": "v1.2.3", "core_repo": "https://example.test/core.git"},
        "dispatcher": {
            "master_ci": {"workflow": "Build", "job": "all-green"},
            "janitor": {"check_suite": "make ci"},
            "janitor_bootstrap": {"recipe": "make hooks"},
            "prepare_toolchain": {"mise": "mise install", "lefthook": "lefthook install"},
            "merge_mode": "squash",
            "sandbox_exempt_marker": "livespec.sandboxExempt",
        },
    }
    resolved = _contract().resolve_integration_contract(declaration=declaration)
    assert resolved.defects == ()
    assert resolved.contract.janitor_check_suite == ("make", "ci")
    assert resolved.contract.sandbox_check_suite == ("make", "ci")
    assert resolved.contract.janitor_bootstrap_recipe == ("make", "hooks")
    assert resolved.contract.prepare_toolchain_mise == ("mise", "install")
    assert resolved.contract.prepare_toolchain_lefthook == ("lefthook", "install")
    assert resolved.contract.core_pinned_ref == "v1.2.3"
    assert resolved.contract.merge_mode == "squash"


def test_a_declaration_is_read_from_the_plugin_block_of_a_config_text() -> None:
    """The resolver grades a declaration; this is the only seam that goes looking for one."""
    declaration = _declaration()
    text = '{ "livespec-orchestrator-beads-fabro": { "compat": { "pinned": "v9" } } }'
    assert declaration.declaration_from_config_text(config_text=text) == {
        "compat": {"pinned": "v9"}
    }


def test_an_unreadable_or_shapeless_config_declares_nothing_rather_than_half_a_thing() -> None:
    """No key could be read, which is every optional field defaulted and every required one named."""
    declaration = _declaration()
    for text in ("not-jsonc", "[]", "{}", '{ "livespec-orchestrator-beads-fabro": 7 }'):
        assert declaration.declaration_from_config_text(config_text=text) == {}


def test_a_dispatcher_scoped_caller_declares_only_the_block_it_actually_read() -> None:
    """Inventing a `compat` answer from a block that cannot hold one is a defect we never file."""
    declaration = _declaration()
    block = {"merge_mode": "squash"}
    assert declaration.declaration_from_dispatcher_block(block=block) == {"dispatcher": block}
