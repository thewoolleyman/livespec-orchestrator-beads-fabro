"""Static guards for the live golden-master shell harness.

The live harness owns Docker lifecycle and the host-to-container credential
projection needed before the Dispatcher can materialize the worker overlay.
These tests pin that brittle shell contract without running Docker.
"""

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "orchestrator-image" / "acceptance-live-golden-master.sh"


def test_live_golden_master_projects_codex_auth_before_dispatch() -> None:
    """The live proof must give the Dispatcher a host Codex credential.

    The Dispatcher reads its own host-side `$HOME/.codex/auth.json`, then writes
    the non-rotatable snapshot into the Fabro sandbox overlay. In the live
    harness that host is the orchestrator container, so the script must copy the
    operator host's single auth.json file into the container before dispatch.
    """
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "${CODEX_HOME:-$HOME/.codex}/auth.json" in text
    assert 'cat > "$HOME/.codex/auth.json"' in text
    assert "docker exec -i" in text
    assert "provision_codex_auth" in text
    assert "provision_codex_auth" in text.split("run_dispatch", maxsplit=1)[0]


def test_live_golden_master_pins_the_successor_codex_acp_at_its_dedicated_prefix() -> None:
    """The version-pin step installs the SUCCESSOR under its dedicated prefix.

    The prefix is the whole point rather than a detail: it is what makes the
    install land at exactly the baked path the rendered adapter invokes, and
    what keeps the two codex-acp packages from contending for one global
    `codex-acp` bin name — so no `--force` is needed, and none may appear.
    """
    text = _SCRIPT.read_text(encoding="utf-8")

    assert (
        "npm install -g --prefix /opt/livespec/codex-acp @agentclientprotocol/codex-acp@%s" in text
    )
    assert "npm install -g @zed-industries/codex-acp" not in text
    assert "npm install -g --force" not in text


def test_live_golden_master_prechecks_the_sandbox_codex_projection() -> None:
    """The injected pre-check asserts the sandbox CODEX_HOME and the baked path.

    It asserts the SNAPSHOT's length rather than its value, so the credential
    can never reach a log, and it names the projected `_SANDBOX_CODEX_HOME`
    literally — a pre-check pointed at the orchestrator container's own
    `~/.codex` would pass while the sandbox projection was broken.
    """
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "test \\$CODEX_HOME = /workspace/.codex" in text
    assert "test \\${#CODEX_AUTH_JSON} -gt 0" in text
    assert "test -x /opt/livespec/codex-acp/bin/codex-acp" in text
    assert "build_sandbox_probe_workflow" in text


def test_live_golden_master_keeps_codex_projection_credential_only() -> None:
    """Never carry the whole host Codex home or the credential as env."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert '-v "$HOME/.codex' not in text
    assert ":/root/.codex" not in text
    assert "-e CODEX" not in text


_SKELETON_SPEC = _REPO_ROOT / "orchestrator-image" / "e2e-skeleton" / "SPECIFICATION"
_SEED_OPENER = "_seed_desc=\"$(cat <<'SEED_DESC'\n"
_SEED_CLOSER = "\nSEED_DESC\n"


def _seed_description() -> str:
    """The throwaway work item's description, verbatim from the harness heredoc."""
    text = _SCRIPT.read_text(encoding="utf-8")
    return text.split(_SEED_OPENER, maxsplit=1)[1].split(_SEED_CLOSER, maxsplit=1)[0]


def _skeleton_h2_headings() -> frozenset[str]:
    """Each H2 of the skeleton spec's top-level files as its verbatim `## <title>` line."""
    return frozenset(
        f"## {match.group(1)}"
        for path in sorted(_SKELETON_SPEC.glob("*.md"))
        for match in re.finditer(
            r"^##\s+(.+?)\s*$", path.read_text(encoding="utf-8"), flags=re.MULTILINE
        )
    )


def test_live_golden_master_seed_references_a_resolvable_skeleton_h2() -> None:
    """The seed's Definition of Done reference resolves against the skeleton spec.

    The dispatcher refuses an item whose `References:` line is not the verbatim
    `## <title>` line of an H2 in the governed spec tree. The harness seeds its
    throwaway item from a heredoc while the spec is a separate fixture, so this
    runs the heredoc's own reference line through the dispatcher's parser against
    the fixture's headings, which keeps the two from drifting apart.
    """
    section = definition_of_done(description=_seed_description())

    assert section.present
    assert section.references
    assert all(reference in _skeleton_h2_headings() for reference in section.references)
