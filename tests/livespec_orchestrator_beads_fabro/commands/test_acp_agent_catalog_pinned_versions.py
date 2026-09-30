"""The pinned-agent-version agreement: the catalog, the renderer, and the image.

Binds `SPECIFICATION/constraints.md` section "Pinned agent versions": "The agent
catalog ... pins an agent version per entry, and those pins are part of the
factory's pinned surface: the sandbox image and the catalog MUST agree on the
baked adapter path for any agent the image bakes (today `codex-acp`)".

THREE PLACES DECLARE THAT PATH AND ALL THREE ARE RESTATED LITERALS. The catalog
entry, the argv renderer's own constant, and the sandbox-image provisioning
script each spell `/opt/livespec/codex-acp/bin/codex-acp` out rather than
importing it, and that is deliberate: `contracts.md` section "Built-in ACP node
defaults" requires a reader to be able to predict the rendered adapter string
from the specification alone, which a chain of imports defeats. Restating it
three times is only safe if something FAILS when the three disagree, and that is
what this module is.

THE IMAGE LEG IS THE ONE THE CONSTRAINT IS ACTUALLY ABOUT. The catalog-versus-
renderer pair could agree perfectly while the image baked the adapter somewhere
else, and the failure that produces is the worst kind available: every dispatch
routed to `codex-acp` renders a correct-looking string naming a path that does
not exist in the sandbox, and the node dies at exec with no configuration error
to point at. So the script that installs the adapter is read as a THIRD,
independent declaration -- it is the only one of the three that describes the
filesystem the adapter actually runs on.

THE VERSION HALF OF THAT CONSTRAINT IS NOT CHECKABLE HERE, and the last case
says so rather than leaving a reader to assume it is. The path is committed three
times; the version the image bakes arrives as an operator argument, so no
committed file declares it. That case asserts the ABSENCE and is written to fail
if the version ever becomes committed -- which is the signal to replace it with
the agreement assertion it cannot make today.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
    CODEX_AGENT_ID,
    builtin_agent_catalog,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import (
    CODEX_ADAPTER_BASE,
    CODEX_ADAPTER_COMMAND,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GOLDEN_MASTER = _REPO_ROOT / "orchestrator-image" / "acceptance-live-golden-master.sh"

# The npm prefix the image installs the adapter under, and the version it pins.
# Read off the provisioning line rather than assumed, so a prefix change is a
# finding rather than a silent pass.
_INSTALL_RE = re.compile(
    r"npm install -g --prefix (?P<prefix>\S+) @agentclientprotocol/codex-acp@(?P<version>\S+?)\\?\""
)


def _golden_master() -> str:
    return _GOLDEN_MASTER.read_text(encoding="utf-8")


def test_the_catalog_and_the_renderer_declare_the_same_baked_path() -> None:
    """Two of the three declarations, compared against each other."""
    entry = builtin_agent_catalog()[CODEX_AGENT_ID]

    assert entry.command == CODEX_ADAPTER_COMMAND


def test_the_catalog_entry_renders_the_ratified_un_pinned_base_string() -> None:
    """The catalog's launch distribution IS the un-pinned base string.

    Section "Built-in ACP node defaults" defines the opt-out as byte-identity
    against that string, so an entry whose posture object or agent mode drifted
    from the renderer's would make the opt-out unreachable through the catalog
    while still rendering something plausible.
    """
    from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
        AcpAdapter,
        render_adapter,
    )

    entry = builtin_agent_catalog()[CODEX_AGENT_ID]
    rendered = render_adapter(
        adapter=AcpAdapter(command=entry.command, env=entry.env, args=entry.args)
    )

    assert rendered == CODEX_ADAPTER_BASE


def test_the_read_only_posture_differs_from_the_write_posture_in_exactly_one_key() -> None:
    """Scenario 90's two postures share every byte but `INITIAL_AGENT_MODE`.

    Asserting the DIFFERENCE rather than each value is what catches a read-only
    environment that had drifted in its posture object too -- which would give a
    reviewer node a sandbox posture nobody chose.
    """
    entry = builtin_agent_catalog()[CODEX_AGENT_ID]
    differing = {
        key
        for key in set(entry.env) | set(entry.read_only_env)
        if entry.env.get(key) != entry.read_only_env.get(key)
    }

    assert differing == {"INITIAL_AGENT_MODE"}
    assert entry.env["INITIAL_AGENT_MODE"] == "agent-full-access"
    assert entry.read_only_env["INITIAL_AGENT_MODE"] == "read-only"


def test_the_sandbox_image_bakes_the_adapter_at_the_path_the_catalog_names() -> None:
    """The third declaration: the filesystem the adapter actually runs on."""
    text = _golden_master()
    match = _INSTALL_RE.search(text)

    assert match is not None, "the provisioning line did not parse; the pattern is mis-aimed"
    prefix = match.group("prefix")
    assert CODEX_ADAPTER_COMMAND.startswith(f"{prefix}/"), (prefix, CODEX_ADAPTER_COMMAND)
    assert f"test -x {CODEX_ADAPTER_COMMAND}" in text


def test_no_committed_file_declares_the_baked_codex_acp_version() -> None:
    """The version half of the constraint is NOT checkable in this repository.

    This case exists to keep that gap visible instead of leaving a reader to
    assume the pin is cross-checked. The path half IS committed three times and
    the cases above bind all three; the VERSION the image bakes is supplied to
    the provisioning script as the operator argument `--codex-acp-version`, so
    the script carries a `printf` placeholder rather than a literal and there is
    nothing in the tree to compare the catalog's pin against.

    The catalog's `version` is therefore a MEASUREMENT RECEIPT -- the value
    measured from inside a live sandbox, recorded so a reader can tell which
    adapter generation the entry describes -- and not a value this suite can
    verify. `SPECIFICATION/constraints.md` section "Pinned agent versions" makes
    changing a pin "a committed change carrying the same rebuild and re-pin duty
    as the Fabro build", and that duty is discharged by the runbook, not here.

    The assertion is on the ABSENCE of a literal, and it is written so that it
    FAILS if the version ever becomes committed -- at which point the honest move
    is to replace this case with the agreement assertion it currently cannot
    make, rather than to widen the pattern until the absence passes again.
    """
    match = _INSTALL_RE.search(_golden_master())

    assert match is not None
    assert match.group("version") == "%s", (
        "the provisioning script now carries a literal codex-acp version; replace this "
        "case with an agreement assertion against the catalog's pin"
    )
    assert "--codex-acp-version" in _golden_master()
