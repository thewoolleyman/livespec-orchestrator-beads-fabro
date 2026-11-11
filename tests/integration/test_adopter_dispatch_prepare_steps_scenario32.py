"""Integration-tier acceptance for the target-local-workflow half of Scenario 32.

Binds the second gherkin block of `SPECIFICATION/scenarios.md` "Scenario 32 —
Adopter-target dispatch compatibility" — an adopter carrying its own
`.fabro/workflows/implement-work-item` workflow, with no `--workflow` override
and no `--workflow-name`, runs the TARGET repository's own toolchain facts and
has no fleet-toolchain prepare constant assumed for it — and the
`SPECIFICATION/contracts.md` target-local-workflow clause it realizes, whose
step (3) resolves that committed directory and whose last sentence keeps prepare
steps "TARGET-TOOLCHAIN facts, not fleet constants".

THE STEPS THAT ACTUALLY RUN COME FROM TWO PLACES, AND THE CASES BELOW COVER
BOTH, because asserting either alone leaves the other free to smuggle a fleet
premise in. The dispatched WORKFLOW carries the prepare scripts, so an adopter's
own chain is only its own if the resolution reaches that adopter's file; and the
orchestrator PROJECTS the typed integration values those scripts read, so a
correctly-resolved adopter workflow would still run `uv` if the projection handed
it one.

THE POSITIVE CONTROL IS THIS REPOSITORY, resolved through the same production
resolver and the same prepare projection, and it is what makes every absence
below evidence rather than decoration: a fleet member's answers carry all three
of the constants the scenario names, so the same instrument that finds nothing in
the adopter's chain is shown finding `uv`, `lefthook` and `livespec_dev_tooling`
in the chain an adopter would otherwise inherit. The bundled run config is read
in the same breath because the two halves cover each other — the projection is
where every fleet constant now reaches a sandbox, and the bundled SCRIPTS are
where one of them used to be invoked outright rather than through an input.
Since work-item bd-ib-xti6q retired that last constant into the `python_sync`
premise, the payload-side half asserts the command-position scan finds NOTHING,
which is the repair; the three-constant evidence is carried by the projection.

THE THREE TOKENS ARE SPELLED HERE RATHER THAN BORROWED, deliberately. The
`check-no-fleet-toolchain-literals` matcher is the right instrument for the
repository-wide ban and is used below as a second one, but its token set does NOT
carry `uv` — so a scan built on it alone cannot return a hit for the constant
this scenario names first, and would report a clean adopter chain for a chain
running `uv sync`.

TWO INSTRUMENTS, BECAUSE THE TWO SURFACES ARE DIFFERENT SHAPES. A prepare SCRIPT
is one shell string, where `uv` is a fleet constant only in command position —
it is two letters long, so a substring scan hits ordinary words. A projected
parameter is an ARGV, already tokenized, where a token equal to `uv` IS command
position. One instrument over both would have to be the weaker of the two, and
the weaker one is what reports a chain running `uv sync` as clean.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    ContractPrepareParameters,
    contract_prepare_parameters,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (
    resolve_repo_integration_contract,
)

from tests.integration.governed_repo_fixtures import (
    ADOPTER,
    PAYLOAD_RUN_CONFIG,
    PROBED_DEFAULT_BRANCH,
    REPO_ROOT,
    fleet_toolchain_token,
)

# The three fleet prepare constants the scenario names, spelled as the ratified
# gherkin spells them.
_FLEET_PREPARE_CONSTANTS: frozenset[str] = frozenset({"uv", "lefthook", "livespec_dev_tooling"})
_SUBSTRING_CONSTANTS: tuple[str, ...] = ("lefthook", "livespec_dev_tooling")
_UV_IN_COMMAND_POSITION = re.compile(r"(?:^|[;&|(]|\bthen\b|\bdo\b|\|\|)\s*uv\b")
# The one fleet-toolchain prepare CONSTANT the committed payload used to carry,
# held here so the command-position matcher keeps a positive case after
# bd-ib-xti6q retired it into the `python_sync` premise. Without it that matcher
# has no input it can hit at all, and a scan that silently stopped matching
# would report every chain clean — the failure mode this module's own header
# names, arriving by attrition rather than by borrowing the wrong matcher.
_RETIRED_UNCONDITIONAL_SYNC = "uv sync --all-groups"
# The adopter's own toolchain: `make` targets, as its committed declaration
# already spells every other integration point.
_ADOPTER_TOOLCHAIN = ("make", "toolchain")
_ADOPTER_HOOKS = ("make", "hooks")
_ADOPTER_HOOK_INSTALL = ("make", "install-hooks")
_SCRIPT_LINE = re.compile(r'^script\s*=\s*"(?P<script>.*)"\s*$', re.MULTILINE)


def _target_local_workflow_text() -> str:
    """An adopter's OWN `implement-work-item` run config, prepare chain and all.

    Its prepare steps are `make` targets plus the typed integration inputs the
    ratified clause expresses a toolchain premise through — never a fleet
    constant — which is exactly the shape the clause describes for "an adopter
    that does carry its own workflow keeps its own prepare chain in it".
    """
    return "\n".join(
        [
            "[workflow]",
            'graph = "workflow.fabro"',
            "",
            "[[run.prepare.steps]]",
            'script = "make toolchain"',
            "",
            "[[run.prepare.steps]]",
            'script = "set -- {{ inputs.prepare_toolchain_mise }}; test $# -eq 0 || \\"$@\\""',
            "",
            "[[run.prepare.steps]]",
            'script = "make install-hooks"',
            "",
        ]
    )


def _adopter_target(*, tmp_path: Path) -> Path:
    """An adopter checkout carrying its OWN committed workflow and declaration.

    The declaration is the COMMITTED adopter fixture's, with only the two
    prepare-toolchain points added: every other integration point stays exactly
    what that fixture declares, so this repository is the same fully-declared
    adopter the rest of this tier exercises rather than a third fixture whose
    answers nothing else agrees with.
    """
    repo = tmp_path / "adopter-target"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_target_local_workflow_text(), encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(_declaration_text(), encoding="utf-8")
    return repo


def _declaration_text() -> str:
    """The committed adopter declaration with both toolchain premises named.

    Both are REAL argvs rather than one empty array, because the schema grades a
    present-but-empty declaration as defective — "present but names no program to
    run" — and the ratified explicit no-op is what an ABSENT key resolves to. A
    fixture declaring one empty would therefore be exercising the defect arm
    while reading as an adopter that declares its toolchain.
    """
    document = json.loads(_jsonc_stripped(text=ADOPTER.config_text))
    dispatcher = document["livespec-orchestrator-beads-fabro"]["dispatcher"]
    dispatcher["prepare_toolchain"] = {
        "mise": list(_ADOPTER_TOOLCHAIN),
        "lefthook": list(_ADOPTER_HOOKS),
    }
    return json.dumps(document, indent=2)


def _jsonc_stripped(*, text: str) -> str:
    """The committed JSONC with its `//` line comments removed, string-safe."""
    return re.sub(r'("(?:\\.|[^"\\])*")|(//[^\n]*)', lambda m: m.group(1) or "", text)


def _prepare_scripts(*, run_config: Path) -> tuple[str, ...]:
    """Every `[[run.prepare.steps]]` script a committed run config declares.

    Read with a line-scoped pattern rather than a TOML parser for the reason
    `_dispatcher_integration_projection` records about the same file: `tomllib`
    is 3.11+ and this family vendors no TOML library, and the run config's shape
    is stable and repository-owned.
    """
    text = run_config.read_text(encoding="utf-8")
    return tuple(match.group("script") for match in _SCRIPT_LINE.finditer(text))


def _constants_in_scripts(*, scripts: Sequence[str]) -> set[str]:
    """Which named constants these SHELL STRINGS invoke, `uv` in command position."""
    found: set[str] = set()
    for script in scripts:
        if _UV_IN_COMMAND_POSITION.search(script) is not None:
            found.add("uv")
        found.update(token for token in _SUBSTRING_CONSTANTS if token in script)
    return found


def _constants_in_argv(*, argv: Sequence[str]) -> set[str]:
    """Which named constants this ARGV names, `uv` as a token of its own."""
    found = {"uv"} if "uv" in argv else set()
    for entry in argv:
        found.update(token for token in _SUBSTRING_CONSTANTS if token in entry)
    return found


def _projected_argv(*, parameters: ContractPrepareParameters) -> tuple[str, ...]:
    """Every token the prepare projection hands a sandbox, as one argv."""
    return (
        *parameters.toolchain_mise,
        *parameters.toolchain_python_sync,
        *parameters.toolchain_lefthook,
        *parameters.conformance_hook_install,
        *parameters.conformance_verify_commit_refuse_hook,
        *parameters.conformance_verify_plugin_resolution,
        parameters.sandbox_exempt_marker,
    )


def test_scenario32_an_adopter_carrying_its_own_workflow_runs_its_own_prepare_chain(
    tmp_path: Path,
) -> None:
    """The resolution reaches the TARGET's own file, and that file's chain is its own.

    Both halves are asserted on one dispatch, because either alone is satisfied
    by a build that fails the other: a resolution reaching the adopter's file
    says nothing about what that file runs, and a fleet-constant-free chain says
    nothing about whether the dispatch would have read it.

    The dispatch names NO `--workflow` and NO `--workflow-name`, which is the
    scenario's own `Given` and the only condition under which step (3) of the
    ratified precedence is reached at all.
    """
    repo = _adopter_target(tmp_path=tmp_path)
    args = argparse.Namespace(workflow=None, workflow_name=None, repo=str(repo))

    resolved = workflow_toml(args=args)
    scripts = _prepare_scripts(run_config=resolved)

    assert resolved == repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
    assert resolved != PAYLOAD_RUN_CONFIG
    assert "make toolchain" in scripts
    assert "make install-hooks" in scripts
    assert _constants_in_scripts(scripts=scripts) == set()
    # The repository-wide ban's OWN matcher as a second instrument, which carries
    # `lefthook` and this fleet's runners but not `uv`.
    assert [line for line in scripts if fleet_toolchain_token(line=line) is not None] == []


def test_scenario32_the_orchestrator_projects_the_adopters_own_toolchain_facts(
    tmp_path: Path,
) -> None:
    """The typed values the adopter's prepare scripts read are the adopter's own.

    The clause expresses a toolchain premise through the integration inputs
    rather than through a workflow copy, so a correctly-resolved adopter chain
    would still run a fleet tool if this projection handed it one. The resolved
    answers are asserted as VALUES — the adopter's own two `make` argvs — because
    a build answering the ratified explicit no-op for both would satisfy the token
    scan exactly as well while discarding the adopter's own toolchain steps.
    """
    repo = _adopter_target(tmp_path=tmp_path)

    resolved = resolve_repo_integration_contract(
        config_text=(repo / ".livespec.jsonc").read_text(encoding="utf-8"),
        default_branch=PROBED_DEFAULT_BRANCH,
    )
    parameters = contract_prepare_parameters(resolved=resolved)
    projected = _projected_argv(parameters=parameters)

    assert resolved.defects == ()
    assert parameters.toolchain_mise == _ADOPTER_TOOLCHAIN
    assert parameters.toolchain_lefthook == _ADOPTER_HOOKS
    assert parameters.conformance_hook_install == _ADOPTER_HOOK_INSTALL
    assert _constants_in_argv(argv=projected) == set()
    assert [line for line in projected if fleet_toolchain_token(line=line) is not None] == []


def test_scenario32_a_fleet_member_names_all_three_constants_through_the_same_seams() -> None:
    """The positive control, and the measurement of what the resolution is FOR.

    THIS repository is a fleet member, resolved through the same production
    contract resolver and the same prepare projection, and its answers name all
    three constants the scenario lists. Without this case every absence above is
    equally consistent with a scan that cannot return a hit at all — which, for
    `uv`, is exactly what borrowing the literal-ban matcher would have produced.

    THE BUNDLED PAYLOAD NO LONGER INVOKES ANY OF THEM, and that is the subject
    of work-item bd-ib-xti6q rather than a weakening of this control. `uv sync
    --all-groups` was the last fleet-toolchain prepare CONSTANT in the committed
    run config, and a dispatch of a governed repository carrying no
    `pyproject.toml` died on it in preparation; it is now the `python_sync` arm
    of `dispatcher.prepare_toolchain`, so a member's `uv` reaches a sandbox
    through the PROJECTION — which the first assertion measures — and through
    nothing else. The command-position scan is therefore asserted EMPTY over the
    payload, which is the repair itself; the one remaining substring hit is the
    INPUT NAME `inputs.prepare_toolchain_lefthook`, a token this payload reads
    rather than a tool it runs.
    """
    member = resolve_repo_integration_contract(
        config_text=(REPO_ROOT / ".livespec.jsonc").read_text(encoding="utf-8"),
        default_branch=PROBED_DEFAULT_BRANCH,
    )
    projected = _projected_argv(parameters=contract_prepare_parameters(resolved=member))
    scripts = _prepare_scripts(run_config=PAYLOAD_RUN_CONFIG)

    assert _constants_in_argv(argv=projected) == _FLEET_PREPARE_CONSTANTS
    # The matcher's own positive control, run on the retired command line: it is
    # what makes the empty payload reading below evidence of the repair rather
    # than of a scan that can no longer return a hit for anything.
    assert _constants_in_scripts(scripts=(_RETIRED_UNCONDITIONAL_SYNC,)) == {"uv"}
    assert [line for line in scripts if _UV_IN_COMMAND_POSITION.search(line) is not None] == []
    assert _constants_in_scripts(scripts=scripts) == {"lefthook"}
