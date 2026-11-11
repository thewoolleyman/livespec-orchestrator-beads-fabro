"""The sandbox version-manager install runs ANONYMOUSLY (work-item bd-ib-bic7hb).

`mise install` resolves the aqua-backed pins in `.mise.toml` through
api.github.com, and mise's aqua backend automatically uses `GITHUB_TOKEN` (or
`GH_TOKEN` / `GITHUB_API_TOKEN`) when one is present. The Dispatcher's
run-config overlay projects an ephemeral App INSTALLATION token as
`GITHUB_TOKEN`, so leaving that variable in scope makes a third-party
public-repo metadata fetch a consumer of the factory's own App-installation
credit — one 5000/hr primary rate-limit bucket shared fleet-wide. When it
empties, the prepare step exits 1 and the run dies before any agent work,
stranding the admitted work-item in `active`.

Reproduced 2026-07-26 inside the sandbox image: in the same second, the
anonymous request for the release URL returned 200 while the credentialed one
returned 403 `API rate limit exceeded for installation ID ...`.

WHERE THE COMMAND LIVES NOW. Since the typed-workflow-inputs carrier
(C5-payload, plan bd-ib-vblnq2) the committed `workflow.toml` spells no fleet
tool: its version-manager prepare step reads `inputs.prepare_toolchain_mise`,
which the Dispatcher renders from this repository's resolved integration
contract — the `dispatcher.prepare_toolchain.mise` argv declared in
`.livespec.jsonc`. So the property is asserted on the RESOLVED value, read
through the same resolver and projection the Dispatcher uses, and on the
payload step that carries it.

Injected defect that makes these RED: drop the `env -u` scrub from the declared
`dispatcher.prepare_toolchain.mise` argv, so mise resolves aqua tools with the
factory credential again.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_prompt_variables,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (
    resolve_repo_integration_contract,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_TOML = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)
_CONFIG = _REPO_ROOT / ".livespec.jsonc"
_MISE_INPUT = "prepare_toolchain_mise"
_SCRUBBED_VARIABLES = ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN")


def _rendered_inputs() -> dict[str, str]:
    """Every sandbox-crossing input value as the Dispatcher would render it for this repo."""
    resolved = resolve_repo_integration_contract(
        config_text=_CONFIG.read_text(encoding="utf-8"), default_branch=None
    )
    return dict(contract_prompt_variables(resolved=resolved))


def _mise_install_command() -> str:
    """The resolved version-manager install command this repository declares."""
    command = _rendered_inputs()[_MISE_INPUT]
    assert "mise install" in command, f"the declared {_MISE_INPUT} does not run mise install"
    return command


def _prepare_scripts() -> list[str]:
    return [
        line.strip()
        for line in _WORKFLOW_TOML.read_text(encoding="utf-8").splitlines()
        if line.startswith("script = ")
    ]


def test_mise_install_scrubs_every_github_credential_variable() -> None:
    """No GitHub credential variable survives into the `mise install` environment."""
    command = _mise_install_command()
    for variable in _SCRUBBED_VARIABLES:
        assert f"-u {variable}" in command, f"{variable} is not scrubbed from the mise install"


def test_the_scrub_wraps_mise_install_itself() -> None:
    """The scrub is applied to `mise install`, not merely mentioned in the command."""
    command = _mise_install_command()
    scrub_at = command.index("env -u")
    install_at = command.index("mise install")
    assert scrub_at < install_at, "the env scrub must precede `mise install` in the same command"


def test_the_payload_step_reads_the_declared_command_and_spells_none_of_its_own() -> None:
    """The prepare step is a projection of the declared argv, not a second copy of it."""
    steps = [step for step in _prepare_scripts() if f"inputs.{_MISE_INPUT}" in step]
    assert len(steps) == 1, f"expected exactly one prepare step reading {_MISE_INPUT}, got {steps}"
    # Whole-word: the token NAME `prepare_toolchain_mise` is not the tool.
    assert re.search(r"(?<![\w-])mise(?![\w-])", steps[0]) is None


def test_the_scrub_is_scoped_to_the_mise_install_step_only() -> None:
    """Every OTHER prepare step and rendered input keeps the full credential environment."""
    other_inputs = [value for name, value in _rendered_inputs().items() if name != _MISE_INPUT]
    other_steps = [step for step in _prepare_scripts() if f"inputs.{_MISE_INPUT}" not in step]
    assert other_steps, "expected other prepare steps to exist"
    assert not [value for value in other_inputs if "env -u" in value]
    assert not [step for step in other_steps if "env -u" in step]
