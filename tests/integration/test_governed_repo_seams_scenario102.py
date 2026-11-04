"""Members-and-adopters-identical is a FAILING TEST, not prose.

Binds `SPECIFICATION/scenarios.md` Scenario 102 and the adopter-and-member-fixtures
bullet of `SPECIFICATION/constraints.md`'s governed-repository integration
constraints. Every case below is one dispatch-path seam -- preflight, contract
resolution, plan build, input rendering, workflow validation, and the sandbox's
prepare parameters with the sandbox itself stubbed -- run through PRODUCTION code
and parametrized over BOTH committed governed-repository fixtures.

WHAT THE ADOPTER LEG BUYS THAT THE MEMBER LEG CANNOT. The member fixture rests on
fleet defaults, so a fleet premise smuggled into the orchestrator agrees with it
and stays invisible; the adopter fixture declares every point through the schema
and carries none of this fleet's tooling, so the same premise has nowhere to be
read from and the seam answers with a literal the adopter never chose. That is
why the last case scans every rendered projection with the literal-ban gate's own
matcher and asserts a fleet token appears on the member leg and on NO adopter
one: an absence-assertion whose instrument is proven able to return a hit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_pipeline_view import (
    resolve_master_ci_pipeline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    ORIGIN_HEAD_ARGV,
    REPO_VIEW_ARGV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import (
    janitor_trust_argv,
    pull_primary_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_install_recipe import (
    DEFAULT_RESOLUTION,
    JanitorBootstrapRecipe,
    hook_install_recipe_present,
    janitor_bootstrap_recipe_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    declaration_from_config_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    FLEET_RECIPE_RUNNER,
    RELEASE_REPOSITORY_MASTER_REF,
    RELEASE_REPOSITORY_RELEASE_REF,
    RELEASE_REPOSITORY_URL,
    UNRESOLVED_NAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    CONTRACT_INPUT_NAMES,
    contract_prepare_parameters,
    contract_prompt_variables,
    contract_workflow_inputs,
    merge_method_flag,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    INTEGRATION_FIELDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_validation import (
    validate_declaration,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_venue import (
    fleet_toolchain_is_the_host_janitor_premise,
    provision_janitor_checkout,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_probe_wiring import (
    resolve_default_branch as probe_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged_pr import (
    merged_pr_list_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_preflight import (
    source_checkout_preflight,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_staleness_gate import (
    latest_release_ref_argv,
    master_ref_argv,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

from tests.integration.governed_repo_fixtures import (
    FLEET_TOOLCHAIN_FILES,
    PAYLOAD_RUN_CONFIG,
    PROBED_DEFAULT_BRANCH,
    GovernedRepo,
    fleet_toolchain_token,
    over_both_fixtures,
)

_ITEM = WorkItem(
    id="fixture-1",
    type="feature",
    status="active",
    title="fixture",
    description="the item each parametrized seam is exercised for",
    origin="freeform",
    gap_id=None,
    rank="a0",
    assignee=None,
    depends_on=(),
    captured_at="2026-08-31T00:00:00Z",
    resolution=None,
    reason=None,
    audit=None,
    superseded_by=None,
)
_MERGED = PrView(
    number=7,
    state="MERGED",
    auto_merge_armed=True,
    merge_state_status="CLEAN",
    merge_sha="cafe01",
)


@over_both_fixtures
def test_the_committed_fixture_carries_the_toolchain_shape_it_claims(
    governed: GovernedRepo,
) -> None:
    """The member carries the whole fleet toolchain; the adopter carries none of it.

    Structurally AND textually. File presence alone would pass an adopter tree
    that had grown a fleet invocation inside a file of its own naming, so the
    whole tree is also read line by line through the literal-ban gate's matcher.
    """
    present = {name for name in FLEET_TOOLCHAIN_FILES if (governed.root / name).is_file()}
    expected = set(FLEET_TOOLCHAIN_FILES) if governed.carries_fleet_toolchain else set()
    tokens = {
        token
        for path in governed.files
        for line in path.read_text(encoding="utf-8").splitlines()
        if (token := fleet_toolchain_token(line=line)) is not None
    }

    assert present == expected
    assert bool(tokens) is governed.carries_fleet_toolchain
    assert (governed.root / ".livespec.jsonc").is_file()
    assert (governed.root / "hooks" / "pre-commit").is_file()


@over_both_fixtures
def test_the_preflight_seam_admits_the_declaration_and_looks_up_its_own_pipeline(
    governed: GovernedRepo,
) -> None:
    """Seam: pre-dispatch. Both fixtures are admitted, each on its OWN pipeline."""
    validation = validate_declaration(
        declaration=declaration_from_config_text(config_text=governed.config_text)
    )
    pipeline = resolve_master_ci_pipeline(cwd=governed.root)

    assert validation.defects == ()
    assert pipeline.defect is None
    assert (pipeline.workflow, pipeline.job) == governed.master_ci


@over_both_fixtures
def test_the_contract_resolution_seam_answers_every_point_with_no_defect(
    governed: GovernedRepo,
) -> None:
    """Seam: contract resolution. The whole closed set resolves for both fixtures."""
    resolved = governed.resolved()

    assert resolved.defects == ()
    assert set(resolved.resolutions) == {field.attribute for field in INTEGRATION_FIELDS}
    assert resolved.contract.janitor_check_suite == governed.janitor_check_suite
    assert resolved.contract.sandbox_check_suite == governed.sandbox_check_suite
    assert resolved.contract.janitor_bootstrap_recipe == governed.bootstrap_recipe
    assert resolved.contract.default_branch == PROBED_DEFAULT_BRANCH


@over_both_fixtures
def test_the_plan_build_seam_projects_the_janitor_off_the_one_resolved_contract(
    governed: GovernedRepo,
) -> None:
    """Seam: plan build. The host janitor argv is a projection, never a second read."""
    plan = _plan(governed=governed)

    assert plan.integration.contract == governed.resolved().contract
    assert plan.janitor == governed.janitor_check_suite
    assert merge_method_flag(resolved=plan.integration) == f"--{governed.merge_mode}"


@over_both_fixtures
def test_the_input_rendering_seam_sends_exactly_what_the_payload_declares(
    governed: GovernedRepo,
) -> None:
    """Seam: input rendering and workflow validation, against the REAL payload.

    The three sets the ratified seam-equivalence clause compares -- what the
    payload declares, what the schema projects, and what the Dispatcher renders
    for THIS repository -- are asserted identical here per fixture, which is the
    per-fixture half of the repo-wide `check-seam-equivalence` gate.
    """
    declared = contract_workflow_inputs(
        committed_text=PAYLOAD_RUN_CONFIG.read_text(encoding="utf-8")
    )
    plan = _plan(governed=governed)
    rendered = {pair.split("=", 1)[0]: pair.split("=", 1)[1] for pair in plan.integration_inputs}

    assert declared == frozenset(CONTRACT_INPUT_NAMES.values())
    assert set(rendered) == set(declared)
    assert rendered == dict(contract_prompt_variables(resolved=plan.integration))


@over_both_fixtures
def test_the_sandbox_seam_receives_the_values_it_never_resolves(
    governed: GovernedRepo,
) -> None:
    """Seam: the sandbox prepare chain, stubbed. It consumes values, never a resolver."""
    parameters = contract_prepare_parameters(resolved=governed.resolved())

    assert parameters.sandbox_exempt_marker == "livespec.sandboxExempt"
    assert parameters.conformance_hook_install == governed.conformance_hook_install
    # The prepare-toolchain premises are the ratified explicit no-op VALUE for
    # both fixtures -- a member's are provisioned by the payload's own chain, and
    # an adopter carries none at all. Neither is an absence anybody inferred.
    assert parameters.toolchain_mise == ()
    assert parameters.toolchain_lefthook == ()


@over_both_fixtures
def test_no_fleet_toolchain_literal_reaches_an_adopter_projection(
    governed: GovernedRepo,
) -> None:
    """The teeth: an undeclared fleet premise fails HERE, not in an adopter's production.

    The member leg is the positive control. It must find a token, because an
    absence reported by an instrument that cannot return a hit is not evidence.
    """
    plan = _plan(governed=governed)
    lines = [
        *plan.janitor,
        *plan.integration_inputs,
        plan.janitor_core_repo_url,
        plan.janitor_core_ref,
        *contract_prepare_parameters(resolved=plan.integration).conformance_hook_install,
    ]
    tokens = {token for line in lines if (token := fleet_toolchain_token(line=line)) is not None}

    assert bool(tokens) is governed.carries_fleet_toolchain


@over_both_fixtures
def test_the_primary_refresh_and_merged_pr_search_name_the_resolved_branch(
    governed: GovernedRepo,
) -> None:
    """Seam: the two argvs that used to pin a branch name this fleet happens to use.

    `pull_primary_argv` carried the fleet runner wrapper AND a shell-string
    fallback to a bare branch name; the merged-PR search pinned its `--base` to
    one. Both now read the plan's resolved `default_branch`, which the fixtures
    probe as a branch NEITHER `master` nor `main` -- so a surviving constant
    cannot pass by agreeing with the answer.
    """
    plan = _plan(governed=governed)

    pull = pull_primary_argv(plan=plan)
    search = merged_pr_list_argv(
        item=_ITEM, default_branch=plan.integration.contract.default_branch
    )

    assert pull == ["git", "-C", str(governed.root), "pull", "--ff-only", "origin", "release"]
    assert search[search.index("--base") + 1] == PROBED_DEFAULT_BRANCH
    assert [line for line in (*pull, *search) if fleet_toolchain_token(line=line) is not None] == []


@over_both_fixtures
def test_the_host_janitor_venue_emits_the_trust_step_only_on_its_own_premise(
    governed: GovernedRepo,
) -> None:
    """Seam: the host-janitor argv SEQUENCE, driven through production provisioning.

    The member leg is the positive control -- it must find the trust step, since
    an absence reported by a sequence that could never contain it is not
    evidence -- and the adopter leg asserts no argv of the whole sequence carries
    a fleet token at all.
    """
    plan = _plan(governed=governed)
    runner = _AlwaysOk()

    outcome = provision_janitor_checkout(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=_Journal(),
        merged=_MERGED,
        recipe=janitor_bootstrap_recipe_from_block(
            block=dispatcher_block(cwd=governed.root),
        ),
    )
    argvs = [argv for argv, _ in runner.calls]

    assert outcome is None
    assert (
        fleet_toolchain_is_the_host_janitor_premise(plan=plan) is governed.carries_fleet_toolchain
    )
    assert (janitor_trust_argv() in argvs) is governed.carries_fleet_toolchain
    tokens = {
        token
        for argv in argvs
        for line in argv
        if (token := fleet_toolchain_token(line=line)) is not None
    }
    assert bool(tokens) is governed.carries_fleet_toolchain


@over_both_fixtures
def test_the_hook_install_re_verification_finds_each_fixture_its_own_recipe(
    governed: GovernedRepo,
) -> None:
    """Seam: the recipe re-verification, whose runner NAME now comes from defaults.

    Each fixture resolves its OWN recipe, and only the member's carries the fleet
    recipe runner. The second half is the discrimination itself, asserted on ONE
    recipe run against both trees so the two legs differ in the repository rather
    than in the input: a fleet-shaped recipe is answered from the member's
    committed justfile and is absent from the adopter's tree, and the name that
    sends it down the justfile route is read from the fleet-defaults module
    rather than from a parser constant of this module's own.

    The justfile route is deliberately the one under test here because it reaches
    no PATH: an invocability answer would depend on which tools this host happens
    to carry, which is not a property of either fixture.
    """
    recipe = janitor_bootstrap_recipe_from_block(block=dispatcher_block(cwd=governed.root))
    fleet_shaped = JanitorBootstrapRecipe(
        command=(FLEET_RECIPE_RUNNER, "install-commit-refuse-hooks"),
        text=f"{FLEET_RECIPE_RUNNER} install-commit-refuse-hooks",
        resolution=DEFAULT_RESOLUTION,
    )

    assert recipe.command == governed.bootstrap_recipe
    assert (FLEET_RECIPE_RUNNER in recipe.command) is governed.carries_fleet_toolchain
    assert (
        hook_install_recipe_present(repo=governed.root, recipe=fleet_shaped)
        is governed.carries_fleet_toolchain
    )


@over_both_fixtures
def test_the_source_preflight_dry_run_targets_the_resolved_branch(
    governed: GovernedRepo,
) -> None:
    """Seam: the pre-plan step, which has no contract to read and resolves its own.

    It runs before a plan exists, so it reaches the SHARED two-route resolver
    rather than the resolved contract -- and, like every other converted site,
    carries no branch-name constant to fall back to.
    """
    runner = _DetachedHead(default_branch=PROBED_DEFAULT_BRANCH)

    outcome = source_checkout_preflight(repo=governed.root, runner=runner)

    assert outcome.refusal is not None
    assert ["git", "push", "--dry-run", "origin", f"HEAD:{PROBED_DEFAULT_BRANCH}"] in runner.argvs
    assert not any("HEAD:master" in argv or "HEAD:main" in argv for argv in runner.argvs)


@over_both_fixtures
def test_the_probe_wiring_seam_reads_the_shared_resolution_and_never_names_a_branch(
    governed: GovernedRepo,
) -> None:
    """Seam: the loop probe's default-branch read, which used to carry its own probe.

    Two arms on one seam, because the converted site answers two questions and a
    regression in either is silent. The RESOLVING arm proves the probe reaches the
    SHARED two-route resolver rather than a private `git symbolic-ref` of its own:
    the runner is asked the ratified `ORIGIN_HEAD_ARGV`, in the fixture's own
    checkout, and answers the branch NEITHER `master` NOR `main` that both
    fixtures probe as -- so a surviving constant cannot pass by agreeing. The
    SILENT arm proves the retired fallback stayed retired: both routes answer
    nothing, and the probe returns the same unresolved sentinel the resolved
    contract renders for an unresolvable required field rather than substituting a
    branch name the repository never chose.
    """
    probed = _TwoRoute(origin_head=f"origin/{PROBED_DEFAULT_BRANCH}\n", repo_view="")
    silent = _TwoRoute(origin_head="\n", repo_view="\n")

    resolved = probe_default_branch(repo=governed.root, runner=probed)
    unresolved = probe_default_branch(repo=governed.root, runner=silent)

    assert resolved == PROBED_DEFAULT_BRANCH
    assert probed.calls == [(list(ORIGIN_HEAD_ARGV), governed.root)]
    assert unresolved == UNRESOLVED_NAME
    assert unresolved not in {PROBED_DEFAULT_BRANCH, "master", "main"}
    assert [argv for argv, _ in silent.calls] == [list(ORIGIN_HEAD_ARGV), list(REPO_VIEW_ARGV)]


@over_both_fixtures
def test_the_currency_gate_probes_this_plugin_and_never_a_governed_repository(
    governed: GovernedRepo,
) -> None:
    """Seam: the staleness gate, whose refs are THIS plugin's own release identity.

    Parametrized like every other seam, and the assertion is what the
    parametrization is for: the argv is byte-identical for both fixtures, because
    the gate asks about the orchestrator's own publishing rather than about the
    repository being dispatched. Its refs are read from the fleet-defaults module
    -- the one place a bare default-branch ref may be spelled.
    """
    assert master_ref_argv() == (
        "git",
        "ls-remote",
        RELEASE_REPOSITORY_URL,
        RELEASE_REPOSITORY_MASTER_REF,
    )
    assert latest_release_ref_argv()[-1] == RELEASE_REPOSITORY_RELEASE_REF
    assert str(governed.root) not in master_ref_argv()


@dataclass(kw_only=True)
class _AlwaysOk:
    """A `CommandRunner` that succeeds, so the WHOLE provisioning sequence is recorded."""

    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (timeout_seconds, env)
        self.calls.append((argv, cwd))
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Journal:
    """The append-only journal seam, collected rather than written to disk."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _DetachedHead:
    """A checkout on a detached HEAD, unreachable from origin, with a named default."""

    default_branch: str
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        self.argvs.append(argv)
        tail = tuple(argv[1:])
        if tail[:2] == ("rev-parse", "--is-inside-work-tree"):
            return CommandResult(exit_code=0, stdout="true\n", stderr="")
        if tail == ("rev-parse", "--abbrev-ref", "HEAD"):
            return CommandResult(exit_code=0, stdout="HEAD\n", stderr="")
        if tail[:1] == ("symbolic-ref",):
            return CommandResult(exit_code=0, stdout=f"origin/{self.default_branch}\n", stderr="")
        if tail[:1] == ("rev-parse",):
            return CommandResult(exit_code=0, stdout="abc123\n", stderr="")
        return CommandResult(exit_code=1, stdout="", stderr="unreachable\n")


@dataclass(kw_only=True)
class _TwoRoute:
    """A checkout answering each ratified default-branch route with a canned stdout.

    Both routes exit 0, so an EMPTY answer is silence rather than a failure -- the
    stricter input, since a resolver that treated a clean-but-empty read as an
    answer would return the empty string instead of falling through.
    """

    origin_head: str
    repo_view: str
    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (timeout_seconds, env)
        self.calls.append((argv, cwd))
        answered = self.origin_head if tuple(argv) == ORIGIN_HEAD_ARGV else self.repo_view
        return CommandResult(exit_code=0, stdout=answered, stderr="")


def _plan(*, governed: GovernedRepo) -> DispatchPlan:
    """One dispatch plan for a fixture, built exactly as the Dispatcher builds one."""
    return build_plan(
        repo=governed.root,
        work_item_id="fixture-1",
        workflow_toml=governed.root / "workflow.toml",
        goal_file=governed.root / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=governed.root / "janitor-checkout",
        config_text=governed.config_text,
        default_branch=PROBED_DEFAULT_BRANCH,
        committed_workflow_text=PAYLOAD_RUN_CONFIG.read_text(encoding="utf-8"),
    )
