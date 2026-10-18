"""The sandbox pack installation is the SAME recipe `just bootstrap` runs (bd-ib-tlmq3m).

The worktree-discipline pack is gitignored -- installed, never tracked -- so a
fresh clone carries none of it by construction. A Fabro sandbox is a fresh full
clone, and until this work-item nothing in its prepare chain installed the pack:
it arrived only as a SIDE EFFECT of the hook-manager pre-commit hook when the
implement agent committed. A run whose implement stage makes no commit of its own
-- which is what a seeded re-dispatch is -- therefore reached its janitor with no
pack, and `check-no-workflow-edits` exited 127 on a missing file. Measured on hp
run 01M515AA906VCTAFFZ5JRAJJKX: all 41 setup commands exited 0 and none of them
installed the pack.

WHAT THIS MODULE ASSERTS, and what it deliberately leaves to its sibling. This is
the RECIPE IDENTITY half of the work-item: that the sandbox installs the pack by
running the one sanctioned installer rather than a second spelling of it. The
sibling `test_dispatcher_sandbox_worktree_pack_prepare_chain` asserts the other
half -- that the prepare chain actually runs it, and only where this fleet's
toolchain is the premise of the sandbox gate.

WHY IDENTITY IS WORTH ITS OWN ASSERTIONS. A respelled installer is the failure
mode this repository has already paid for twice over: `SPECIFICATION/
constraints.md`'s fleet-toolchain-literal ban exists because every fleet premise
used to sit at its point of use, and each copy drifted from its twin because
nothing bound them. A hand-spelled `mise exec -- just install-worktree-pack` here
would pass every behavioural test while being exactly the drift-prone copy the
defaults module exists to retire -- so the argv is asserted to be COMPOSED from
the fleet runner names, and the recipe is asserted to be the one `just bootstrap`
itself delegates to, read out of the shipped files rather than retyped.

THE TWO CONSTANTS ARE EQUAL AND STILL SEPARATE, which is the house pattern rather
than an oversight: `CONFORMANCE_NO_OP` and `TOOLCHAIN_NO_OP` are the same empty
argv and are spelled apart "because they answer different premises and one of them
changing must not silently change the other". The host janitor's per-checkout
provisioning and the sandbox's are two premises of two venues, so the equality is
asserted as a MIRROR while each name stands on its own.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_integration_defaults

_SANDBOX_DEFAULT = "SANDBOX_CHECKOUT_PROVISION_DEFAULT"
_JANITOR_DEFAULT = "JANITOR_CHECKOUT_PROVISION_DEFAULT"
# The pack installer recipe, named ONCE here and then verified against the shipped
# justfile and the shipped bootstrap delegate rather than trusted.
_RECIPE = "install-worktree-pack"
_JUSTFILE = Path("justfile")
# `just bootstrap` is a thin delegator to this script, so the recipe `bootstrap`
# actually runs is read out of the script rather than out of the recipe body.
_BOOTSTRAP_DELEGATE = Path("dev-tooling/just-bootstrap.sh")


def test_the_sandbox_pack_installation_is_composed_from_the_fleet_runner_names() -> None:
    """The argv is BUILT from the runner names, not respelled as a literal.

    The expectation is assembled from `FLEET_TOOL_RUNNER` and
    `FLEET_RECIPE_RUNNER` deliberately: an expectation that spelled the two tool
    names itself would pass against a hand-written literal in the defaults module,
    which is precisely the drift-prone copy this fleet bans.
    """
    assert hasattr(
        _dispatcher_integration_defaults, _SANDBOX_DEFAULT
    ), f"the sandbox prepare chain has no pack-provisioning default named {_SANDBOX_DEFAULT}"

    argv = getattr(_dispatcher_integration_defaults, _SANDBOX_DEFAULT)

    assert argv == (
        _dispatcher_integration_defaults.FLEET_TOOL_RUNNER,
        "exec",
        "--",
        _dispatcher_integration_defaults.FLEET_RECIPE_RUNNER,
        _RECIPE,
    )


def test_the_recipe_is_the_one_just_bootstrap_delegates_to() -> None:
    """ "The same recipe `just bootstrap` runs" — read off the shipped files.

    Both halves earn their place. The justfile check says the recipe EXISTS, so a
    default naming a recipe this repository never declared fails here rather than
    at `exit 127` inside a sandbox. The delegate check says it is the recipe
    BOOTSTRAP runs, which is the clause's actual wording — a recipe that merely
    exists could still be a second installer standing beside the sanctioned one.
    """
    argv = getattr(_dispatcher_integration_defaults, _SANDBOX_DEFAULT)
    recipe = argv[-1]
    runner = _dispatcher_integration_defaults.FLEET_RECIPE_RUNNER

    declared = re.compile(rf"(?m)^{re.escape(recipe)}:\s*$")
    assert (
        declared.search(_JUSTFILE.read_text(encoding="utf-8")) is not None
    ), f"the root justfile declares no `{recipe}` recipe"

    delegate = _BOOTSTRAP_DELEGATE.read_text(encoding="utf-8")
    invoked = re.compile(rf"(?m)^{re.escape(runner)} {re.escape(recipe)}\s*$")
    assert (
        invoked.search(delegate) is not None
    ), f"`{runner} {recipe}` is not what the bootstrap delegate runs:\n{delegate}"


def test_it_mirrors_the_host_janitor_premise_as_its_own_named_constant() -> None:
    """Same invocation as the host janitor's per-checkout provisioning, named apart.

    The equality is the MIRROR the work-item asks for: the host janitor already
    provisions its fresh checkout this way, because a freshly added worktree
    carries no pack either. The separate export is what keeps the two premises
    independently changeable — the same reasoning the defaults module records for
    `CONFORMANCE_NO_OP` beside `TOOLCHAIN_NO_OP`.
    """
    exported = set(_dispatcher_integration_defaults.__all__)

    assert {_SANDBOX_DEFAULT, _JANITOR_DEFAULT} <= exported
    assert getattr(_dispatcher_integration_defaults, _SANDBOX_DEFAULT) == getattr(
        _dispatcher_integration_defaults, _JANITOR_DEFAULT
    )
