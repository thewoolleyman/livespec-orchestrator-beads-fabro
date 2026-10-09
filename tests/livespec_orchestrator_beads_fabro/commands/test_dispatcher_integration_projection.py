"""The contract resolves ONCE at plan build and PROJECTS into every seam.

`SPECIFICATION/contracts.md`'s resolve-once-project-everywhere clause and
Scenario 100. Every case here asks the same question of a different seam: does
this value come off the ONE `ResolvedIntegrationContract` the plan carries and
the dispatch record journals, or did the seam resolve one of its own?

The distinction is invisible in a value comparison -- a re-derivation from the
same configuration usually produces the same bytes -- so the cases assert the
MECHANISM: that the plan carries the object, that the journal carries it, that a
seam's answer changes when the CONTRACT changes rather than when configuration
does, and that no seam takes a probe of its own.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
    append_dispatch_id_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    dispatch_fabro_run_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_binary_record import (
    EngineBinary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import pr_arm_argv
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_contract import (
    ResolvedIntegrationContract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_INTERNAL_ARGV,
    JANITOR_CHECK_SUITE_DEFAULT,
    MERGE_MODE_DEFAULT,
    SANDBOX_CHECK_SUITE_DEFAULT,
    SANDBOX_EXEMPT_MARKER_DEFAULT,
    UNRESOLVED_NAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    CONTRACT_INPUT_NAMES,
    contract_prepare_parameters,
    contract_prompt_variables,
    contract_run_inputs,
    contract_workflow_inputs,
    integration_contract_journal_record,
    merge_method_flag,
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (
    resolve_repo_integration_contract,
)

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"


def _config(*, dispatcher: dict[str, object] | None = None, pinned: str | None = "master") -> str:
    """A committed `.livespec.jsonc` text declaring the block the schema reads."""
    compat: dict[str, object] = {} if pinned is None else {"pinned": pinned}
    return json.dumps({_PLUGIN_BLOCK: {"compat": compat, "dispatcher": dispatcher or {}}})


def _plan(
    *,
    repo: Path,
    config_text: str | None = None,
    default_branch: str | None = "master",
    janitor: tuple[str, ...] | None = None,
    committed_workflow_text: str = "",
) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=janitor,
        janitor_checkout=repo / "janitor-co",
        config_text=_config() if config_text is None else config_text,
        default_branch=default_branch,
        committed_workflow_text=committed_workflow_text,
    )


@dataclass(kw_only=True)
class _Runner:
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="", stderr="")


def test_the_dispatch_plan_carries_one_resolved_integration_contract(tmp_path: Path) -> None:
    """Criterion 1: the frozen contract is a FIELD of the plan, not a re-read."""
    plan = _plan(repo=tmp_path)

    assert isinstance(plan.integration, ResolvedIntegrationContract)
    assert plan.integration.contract.core_pinned_ref == "master"
    assert plan.integration.contract.default_branch == "master"
    # Every field of the closed set resolved to an arm, so a seam can ask about
    # any point without going back to configuration for it.
    assert set(plan.integration.resolutions) == {
        field.attribute
        for field in importlib.import_module(
            "livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema"
        ).INTEGRATION_FIELDS
    }


def test_a_plan_built_with_no_declaration_carries_the_fail_closed_contract(tmp_path: Path) -> None:
    """The undeclared default is DEFECTIVE on both required fields, never plausible."""
    plan = _plan(repo=tmp_path, config_text="{}", default_branch=None)

    assert plan.integration.contract.core_pinned_ref == UNRESOLVED_NAME
    assert plan.integration.contract.default_branch == UNRESOLVED_NAME
    assert {defect.key for defect in plan.integration.defects} >= {"default_branch"}
    # The plan's own core fields carry the sentinel too, so the post-merge flow
    # degrades naming the declaration rather than cloning a moving tip.
    assert plan.janitor_core_ref == UNRESOLVED_NAME


def test_the_dispatch_record_journals_the_resolved_contract(tmp_path: Path) -> None:
    """Criterion 2: the pre-run record carries the contract, with each field's arm."""
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    plan = _plan(repo=tmp_path, config_text=_config(dispatcher={"merge_mode": "squash"}))

    append_dispatch_id_record(
        journal=journal,
        work_item_id="x-1",
        identity=DispatchJournalIdentity(dispatch_id="d-1", dispatch_factory=None),
        engine=EngineBinary(path="/global/fabro", version="fabro 0.254.0"),
        started_at_epoch=1.0,
        workflow_toml=tmp_path / "wf.toml",
        workflow_name="implement-work-item",
        integration=plan.integration,
        merge_hold=plan.merge_hold,
    )

    record = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8").strip())
    contract = cast("dict[str, object]", record["integration_contract"])
    fields = cast("dict[str, dict[str, object]]", contract["fields"])
    assert contract["schema_version"] == plan.integration.contract.schema_version
    assert fields["merge_mode"] == {
        "key": "dispatcher.merge_mode",
        "arm": "declared",
        "value": "squash",
    }
    assert fields["janitor_check_suite"]["arm"] == "fleet-default"
    assert contract["defects"] == []


def test_the_journal_record_names_every_defective_point_with_its_reason() -> None:
    """A defective field journals a null value and lands in the defect list."""
    resolved = resolve_repo_integration_contract(config_text="{}", default_branch=None)

    record = integration_contract_journal_record(resolved=resolved)
    contract = cast("dict[str, object]", record["integration_contract"])
    fields = cast("dict[str, dict[str, object]]", contract["fields"])
    defects = cast("list[dict[str, str]]", contract["defects"])

    assert fields["default_branch"] == {
        "key": "default_branch",
        "arm": "defective",
        "value": None,
    }
    assert {defect["key"] for defect in defects} == {
        "default_branch",
        f"{_PLUGIN_BLOCK}.compat.pinned",
    }
    assert all(defect["reason"] for defect in defects)


def test_the_host_janitor_argv_is_rendered_from_the_resolved_contract(tmp_path: Path) -> None:
    """Criterion 3: the declared check-suite reaches the janitor through the contract."""
    declared = _plan(
        repo=tmp_path,
        config_text=_config(dispatcher={"janitor": {"check_suite": "make ci"}}),
        janitor=("ignored", "override"),
    )
    defaulted = _plan(repo=tmp_path, janitor=("make", "override"))

    # A DECLARED check-suite is invoked verbatim and outranks `--janitor` ...
    assert declared.janitor == ("make", "ci")
    # ... while the override is scoped to a repository that declared none.
    assert defaulted.janitor == ("make", "override")
    assert _plan(repo=tmp_path).janitor == JANITOR_CHECK_SUITE_DEFAULT


def test_the_janitor_venue_resolves_its_branch_without_a_probe(tmp_path: Path) -> None:
    """Criterion 4: the venue reads `default_branch` off the contract, not from git.

    The runner RECORDS every command it is handed, so the two routes the ratified
    default-branch resolution would take are absent by observation rather than by
    the value merely agreeing with the contract it was meant to read.
    """
    venue_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_venue"
    )
    plan = _plan(repo=tmp_path, default_branch="main")
    unprobed = _Runner()
    confirming = _Runner()

    venue = venue_module.resolve_janitor_venue(plan=plan, runner=unprobed, merge_sha=None)
    confirmed = venue_module.resolve_janitor_venue(plan=plan, runner=confirming, merge_sha="c0ffee")

    assert (venue.ref, venue.defect) == ("origin/main", None)
    assert unprobed.calls == []
    # The ONE command the venue still runs is the merge-containment probe, at
    # the tip the contract named -- never a resolution of the branch itself.
    assert confirmed.ref == "origin/main"
    assert [argv[3:] for argv in confirming.calls] == [
        ["merge-base", "--is-ancestor", "c0ffee", "origin/main"]
    ]
    assert not [argv for argv in confirming.calls if "symbolic-ref" in argv]


def test_the_declared_core_provisioning_is_re_homed_on_the_contract(tmp_path: Path) -> None:
    """Criterion 5: the plan's core ref and clone repository come off the contract."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_core_provisioning_view"
    )
    plan = _plan(
        repo=tmp_path,
        config_text=json.dumps(
            {
                _PLUGIN_BLOCK: {
                    "compat": {"pinned": "v9.9.9", "core_repo": "https://example.test/core.git"}
                }
            }
        ),
    )

    provisioning = module.janitor_core_provisioning_from_contract(resolved=plan.integration)

    assert (provisioning.ref, provisioning.repo_url) == (
        "v9.9.9",
        "https://example.test/core.git",
    )
    assert provisioning.defect is None
    assert (plan.janitor_core_ref, plan.janitor_core_repo_url) == (
        provisioning.ref,
        provisioning.repo_url,
    )


def test_prompt_variables_project_every_sandbox_facing_field() -> None:
    """Criterion 6: ONE mapping is what the inputs, prompts and prepare steps read."""
    resolved = resolve_repo_integration_contract(config_text=_config(), default_branch="trunk")

    variables = contract_prompt_variables(resolved=resolved)

    assert set(variables) == set(CONTRACT_INPUT_NAMES.values())
    # Command-shaped points cross as ONE shell word-list, joined here and nowhere else.
    assert variables["sandbox_check_suite"] == " ".join(SANDBOX_CHECK_SUITE_DEFAULT)
    assert variables["prepare_toolchain_mise"] == ""
    assert variables["sandbox_exempt_marker"] == SANDBOX_EXEMPT_MARKER_DEFAULT
    assert variables["default_branch"] == "trunk"
    assert variables["merge_mode"] == MERGE_MODE_DEFAULT


def test_run_inputs_are_gated_on_the_input_names_the_workflow_declares() -> None:
    """fabro rejects an input a workflow does not declare, so the projection intersects."""
    resolved = resolve_repo_integration_contract(config_text=_config(), default_branch="trunk")
    declares = '[run.inputs]\ndefault_branch = "master"\nimplement_adapter = "npx thing"\n'

    assert contract_run_inputs(resolved=resolved, declared=()) == ()
    assert contract_run_inputs(
        resolved=resolved, declared=contract_workflow_inputs(committed_text=declares)
    ) == ("default_branch=trunk",)
    # The generic scan sees EVERY declared input; only the contract view filters.
    assert set(workflow_declared_inputs(committed_text=declares)) == {
        "default_branch",
        "implement_adapter",
    }
    assert workflow_declared_inputs(committed_text="no table here") == {}
    # A BARE TOML scalar is a declaration too. Two of the three per-item policy
    # inputs are not strings, so a quoted-only scan would report a payload
    # declaring them as declaring neither -- an instrument that cannot return
    # the hit its caller is looking for.
    bare = '[run.inputs]\nmerge_hold = false\nreview_fix_visit_cap = 4\ndefault_branch = "trunk"\n'
    assert workflow_declared_inputs(committed_text=bare) == {
        "merge_hold": "false",
        "review_fix_visit_cap": "4",
        "default_branch": "trunk",
    }
    # The contract view still filters to its own closed name set, so widening
    # the scan did not widen what the Dispatcher sends.
    assert contract_workflow_inputs(committed_text=bare) == frozenset({"default_branch"})


def test_the_dispatch_renders_the_contract_inputs_its_workflow_can_receive(tmp_path: Path) -> None:
    """The plan carries the intersected pairs, and the `fabro run` argv renders them."""
    plan = _plan(
        repo=tmp_path,
        committed_workflow_text='[run.inputs]\nsandbox_exempt_marker = "x"\n',
    )

    assert plan.integration_inputs == (f"sandbox_exempt_marker={SANDBOX_EXEMPT_MARKER_DEFAULT}",)
    inputs = dispatch_fabro_run_inputs(plan=plan)
    assert f"sandbox_exempt_marker={SANDBOX_EXEMPT_MARKER_DEFAULT}" in inputs
    # A workflow declaring none of them is sent none of them. The per-item
    # POLICY inputs ride every dispatch regardless, because they project the
    # item's own policy rather than this repository's integration contract.
    assert dispatch_fabro_run_inputs(plan=_plan(repo=tmp_path)) == (
        f"review_fix_visit_cap={plan.review_fix_visit_cap}",
        f"merge_on_review_cap_outcome={plan.merge_on_review_cap_outcome}",
        "merge_hold=false",
    )


def test_prepare_parameters_project_the_marker_and_the_toolchain_premises() -> None:
    """The prepare chain's values are the contract's, with the no-op as a VALUE."""
    declared = resolve_repo_integration_contract(
        config_text=_config(
            dispatcher={"prepare_toolchain": {"mise": "mise install", "lefthook": ["lefthook"]}}
        ),
        default_branch="master",
    )
    absent = resolve_repo_integration_contract(config_text=_config(), default_branch="master")

    assert contract_prepare_parameters(resolved=declared).toolchain_mise == ("mise", "install")
    assert contract_prepare_parameters(resolved=declared).toolchain_lefthook == ("lefthook",)
    assert contract_prepare_parameters(resolved=absent).toolchain_mise == ()
    assert (
        contract_prepare_parameters(resolved=absent).sandbox_exempt_marker
        == SANDBOX_EXEMPT_MARKER_DEFAULT
    )


def test_prepare_parameters_carry_the_three_conformance_premises() -> None:
    """The baseline-gate prepare steps are values off the contract, no-op included."""
    declared = resolve_repo_integration_contract(
        config_text=_config(
            dispatcher={
                "conformance": {
                    "hook_install": {"mode": "shell_argv", "argv": ["make", "hooks"]},
                    "verify_plugin_resolution": {"mode": "internal_livespec_dev_tooling"},
                }
            }
        ),
        default_branch="master",
    )
    parameters = contract_prepare_parameters(resolved=declared)

    assert parameters.conformance_hook_install == ("make", "hooks")
    assert parameters.conformance_verify_plugin_resolution == (
        CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_INTERNAL_ARGV
    )
    # The premise this repository left unwritten carries the explicit no-op.
    assert parameters.conformance_verify_commit_refuse_hook == ()


def test_the_conformance_premises_cross_into_the_sandbox_as_named_inputs() -> None:
    """An argv crosses shlex-joined as one scalar; the no-op crosses as the empty string."""
    resolved = resolve_repo_integration_contract(
        config_text=_config(
            dispatcher={
                "conformance": {
                    "hook_install": {"mode": "shell_argv", "argv": ["make", "install hooks"]}
                }
            }
        ),
        default_branch="trunk",
    )

    variables = contract_prompt_variables(resolved=resolved)

    # The input NAME equals the schema attribute, which is what makes the
    # rendered-input set and the workflow's token set comparable at all.
    assert {
        attribute: name
        for attribute, name in CONTRACT_INPUT_NAMES.items()
        if attribute.startswith("conformance_")
    } == {
        "conformance_hook_install": "conformance_hook_install",
        "conformance_verify_commit_refuse_hook": "conformance_verify_commit_refuse_hook",
        "conformance_verify_plugin_resolution": "conformance_verify_plugin_resolution",
    }
    assert variables["conformance_hook_install"] == "make 'install hooks'"
    assert variables["conformance_verify_plugin_resolution"] == ""


def test_the_dispatch_record_reports_each_conformance_premises_mode() -> None:
    """The value cannot say which mode produced it; the record must, so it does."""
    resolved = resolve_repo_integration_contract(
        config_text=_config(
            dispatcher={
                "conformance": {
                    "hook_install": {"mode": "no_op"},
                    "verify_commit_refuse_hook": {"mode": "not-a-mode"},
                }
            }
        ),
        default_branch="master",
    )

    record = integration_contract_journal_record(resolved=resolved)
    contract = cast("dict[str, object]", record["integration_contract"])
    fields = cast("dict[str, dict[str, object]]", contract["fields"])

    assert fields["conformance_hook_install"] == {
        "key": "dispatcher.conformance.hook_install",
        "arm": "declared",
        "value": "",
        "mode": "no_op",
    }
    # The absent premise resolves to the SAME empty value; only arm and mode
    # distinguish a chosen skip from one nobody wrote.
    assert fields["conformance_verify_plugin_resolution"]["arm"] == "fleet-default"
    assert fields["conformance_verify_plugin_resolution"]["mode"] == "no_op"
    assert fields["conformance_verify_commit_refuse_hook"]["arm"] == "defective"
    assert fields["conformance_verify_commit_refuse_hook"]["mode"] is None
    # A field that is no conformance premise carries no mode key at all.
    assert "mode" not in fields["merge_mode"]


def test_the_resolved_merge_mode_projects_to_the_gh_pr_merge_method_flag(tmp_path: Path) -> None:
    """Criterion 7: the auto-merge argv names the DECLARED strategy, not `--rebase`."""
    squash = _plan(repo=tmp_path, config_text=_config(dispatcher={"merge_mode": "squash"}))
    conventional = _plan(repo=tmp_path)

    assert pr_arm_argv(plan=squash, number=7) == [
        "gh",
        "pr",
        "merge",
        "7",
        "--squash",
        "--auto",
        "--delete-branch",
    ]
    assert pr_arm_argv(plan=conventional, number=7)[4] == "--rebase"


def test_an_unresolvable_merge_mode_arms_no_method_rather_than_a_strategy(tmp_path: Path) -> None:
    """A present-but-unusable declaration refuses; it never slides onto the convention."""
    defective = _plan(repo=tmp_path, config_text=_config(dispatcher={"merge_mode": "fast-forward"}))

    assert merge_method_flag(resolved=defective.integration) is None
    assert pr_arm_argv(plan=defective, number=7) == [
        "gh",
        "pr",
        "merge",
        "7",
        "--auto",
        "--delete-branch",
    ]
