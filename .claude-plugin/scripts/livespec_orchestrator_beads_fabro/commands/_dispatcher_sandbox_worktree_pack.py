"""The worktree-discipline pack every fleet-default sandbox installs before any check.

WHY THE STEP EXISTS (work-item bd-ib-tlmq3m, Scenarios 30 and 96). The pack --
`check-no-workflow-edits.sh`, `worktree-lib.sh`, `branch-protection.sh`, and the
two `.just` fragments the root justfile `import?`s -- is GITIGNORED: it is
installed, never tracked. A Fabro sandbox is a fresh full clone, so it carries
none of the pack by construction, and nothing in the committed prepare chain
installed it.

What made that survivable for so long is also what made it invisible: the pack
arrived as a SIDE EFFECT. The hook-manager's pre-commit hook runs
`install-worktree-pack` as its first step, so the implement agent's first commit
provisioned the pack, and by the time the janitor node ran its check suite the
pack was there. A run whose implement stage makes NO commit of its own never
fired that hook -- and that is exactly what a seeded re-dispatch is, since it
reuses already-reviewed commits.

MEASURED on hp run 01M515AA906VCTAFFZ5JRAJJKX (dispatch 691c18b6b5e04cbdbccc2f85,
work-item bd-ib-sufca7, 2026-10-16). All 41 setup commands exited 0 and none
installed the pack; janitor@1 then failed on exactly one target --
`bash dev-tooling/check-no-workflow-edits.sh: No such file or directory`, with the
recipe runner reporting `check-no-workflow-edits` failed with exit code 127. A fix
visit ran `install-worktree-pack` by hand and the full aggregate passed 93
targets. The interim mitigation was a dispatch RIDER telling the implement stage
to run the installer; this step is what retires that rider.

WHY THE OVERLAY AND NOT `workflow.toml`. Two independent reasons, either of which
would decide it. The committed run config is FORKED per repository --
`_dispatcher_paths.workflow_toml` resolves a dispatch target's own copy ahead of
the bundled one -- so a prepare step written into the bundle covers one consumer
and silently omits the rest, which is the rationale
`_dispatcher_default_branch_fetch` and `_dispatcher_factory_provenance` record.
And `constraints.md`'s fleet-toolchain-literal ban SCANS that payload, so this
fleet's recipe runner cannot be spelled there at all: the invocation has to arrive
from the fleet-defaults module, which is where `SANDBOX_CHECKOUT_PROVISION_DEFAULT`
lives and why this module composes nothing of its own.

WHY A MATERIALIZED STEP IS LATE ENOUGH, which is the half most easily "improved"
into a defect. Every Dispatcher-materialized block is appended AFTER the committed
chain, and that is a REQUIREMENT here rather than an accident: the recipe runs
`uv run python -m livespec_dev_tooling.install_worktree_pack`, so it needs the
committed `uv sync --all-groups` to have populated the sandbox virtual environment
and the committed version-manager step to have installed the runner. Rendering it
earlier -- ahead of the dispatch-base fetch, say, where the "as early as possible"
instinct points -- fails the prepare step and kills the run before any work.

It is still ahead of every step that READS the pack, which is what the work-item
asks: no prepare step reads it, and the three consumers that do -- the implement
agent's own in-session check suite, `pr_refresh`'s declared gate, and the janitor
node -- all run after the whole prepare chain.

AND IT IS A FLEET PREMISE, NOT AN OBLIGATION. The pack is this fleet's own
dev-tooling artifact, and only this fleet's own check suite reads it, so the step
renders only where the SANDBOX GATE ITSELF resolved to the fleet default. A
repository that declares its own sandbox check suite is declaring that it owns
what runs in that venue, and it owns that venue's provisioning with it -- exactly
as `JANITOR_CHECK_SUITE_DEFAULT` provisions INSIDE its own suite. Imposing this
recipe there would run a recipe that repository may not have, and a failing
prepare step kills every one of its dispatches.

NO WORKTREE EXCLUSION IS RENDERED, and that is deliberate rather than an omission
of the discipline `_dispatcher_sandbox_worktree_exclude` owns. That renderer
exists for Dispatcher-materialized paths git would otherwise stage, and every pack
member is already named in the governed repository's own tracked `.gitignore` --
which is the same fact that makes the pack absent in the first place. A sandbox
whose check suite is the fleet default is a repository that gitignores the pack,
so there is nothing for an exclusion to hide.
"""

from __future__ import annotations

import json
import shlex

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_contract import (
    ResolvedIntegrationContract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    SANDBOX_CHECKOUT_PROVISION_DEFAULT,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_resolver import (
    FleetDefault,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    SANDBOX_CHECK_SUITE_FIELD,
)

__all__: list[str] = [
    "fleet_toolchain_is_the_sandbox_gate_premise",
    "sandbox_worktree_pack_prepare_steps_block",
]


def fleet_toolchain_is_the_sandbox_gate_premise(*, resolved: ResolvedIntegrationContract) -> bool:
    """Whether the in-sandbox gate's own check suite rests on THIS fleet's toolchain.

    The sandbox runs ONE declared command that reads the worktree-discipline pack:
    its check suite. Where that field resolved to the `FleetDefault` arm the
    repository declared nothing there and inherited this fleet's own invocation, so
    the fleet toolchain IS the premise of that gate and provisioning the pack is
    part of provisioning it. Where it resolved `Declared`, the sandbox runs the
    repository's own command and this fleet's tooling is not a premise of anything
    about it.

    THE ARM IS WHAT IS READ, NEVER THE VALUE -- the same discipline
    `fleet_toolchain_is_the_host_janitor_premise` keeps one venue over: a
    repository is free to declare exactly the fleet convention, and a value
    comparison would read that deliberate declaration as an inheritance. The arm
    comes off the plan's ONE resolved contract, so this cannot disagree with the
    resolution the dispatch record journaled.

    This reads the SANDBOX field alone, where the host-janitor premise reads two.
    That is not a narrowing: the janitor venue runs a bootstrap recipe BESIDE its
    suite, and either inheriting makes the toolchain its premise, while the sandbox
    venue's only pack-reading command is the suite itself.
    """
    return isinstance(resolved.resolutions[SANDBOX_CHECK_SUITE_FIELD.attribute], FleetDefault)


def sandbox_worktree_pack_prepare_steps_block(*, provision: bool) -> str:
    """Render the pack-provisioning `[[run.prepare.steps]]` block.

    Empty string when the fleet toolchain is not the sandbox gate's premise, which
    renders exactly the overlay a repository owning its own sandbox gate received
    before this step existed -- and which is also what a direct caller that wires
    nothing gets, since the overlay's parameter defaults off.

    The argv is read from the fleet-defaults module and `shlex.join`-ed rather than
    spelled, so the step runs the one sanctioned installer; the whole script is
    then `json.dumps`-ed to TOML-quote it, matching every sibling block in the
    overlay.

    It carries NO `|| true`. The recipe is idempotent, so a repeat is free, but a
    failure means the sandbox has no pack -- and discovering that in preparation
    is cheaper than discovering it at the janitor, which is the whole defect being
    closed.
    """
    if not provision:
        return ""
    script = shlex.join(SANDBOX_CHECKOUT_PROVISION_DEFAULT)
    lines = [
        "",
        "# --- Dispatcher-materialized worktree-discipline pack provisioning: the",
        "# --- pack is gitignored, so this fresh clone carries none of it, and the",
        "# --- committed chain never installed it — it used to arrive only as a side",
        "# --- effect of the implement agent's first commit, so a run that makes no",
        "# --- commit reached its janitor with no pack and exited 127 on a pack",
        "# --- member. Rendered only where the sandbox gate resolved to this fleet's",
        "# --- own check suite, and after the committed chain that provisions the",
        "# --- virtual environment this recipe runs through (bd-ib-tlmq3m) ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"
