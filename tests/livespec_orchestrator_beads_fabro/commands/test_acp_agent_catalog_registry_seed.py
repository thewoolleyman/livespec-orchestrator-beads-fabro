"""The registry-seeded catalog entries, read against the registry snapshot itself.

Binds the seeding half of `SPECIFICATION/contracts.md` section "Agent and model
catalogs": every entry carries "the launch distribution rendered from the
registry's `npx`, `uvx` or per-platform `binary` distribution at a pinned agent
version, in the manual-form shape (`command`, `args`, `env`)", and "the catalog
MUST record the registry snapshot digest and the date it was seeded from".

THE REGISTRY DOCUMENTS ARE COMMITTED AS A FIXTURE, AND THAT IS THE WHOLE POINT.
A case restating the expected command as a literal is a tautology against the
module -- it passes for whatever the catalog happens to say, including the
`@agentclientprotocol/<adapter>` npx names three entries carried until
2026-10-06, none of which any registry has ever published. So the expected bytes
are RENDERED HERE from the registry's own `distribution` block, read off
`tests/fixtures/acp_registry_snapshot/`, which holds the verbatim `agent.json`
documents of the ratified five ids at the pinned registry commit. A catalog entry
that drifts from the registry now disagrees with the registry's own bytes.

THE RECORDED DIGEST IS CHECKED AGAINST THOSE SAME BYTES rather than taken on
trust. `REGISTRY_SNAPSHOT_DIGEST` is a transcribed literal -- it has to be, since
a dispatch may not fetch the registry to re-derive it -- and a transcribed
literal with nothing to compare it against is indistinguishable from a typo. The
recipe is re-run here over the committed snapshot, so a re-seed that updates the
documents and forgets the digest, or updates the digest and forgets the
documents, fails rather than shipping a snapshot identity that names neither.

ONLY THREE OF THE FIVE ARE ASSERTED AGAINST THE REGISTRY'S DISTRIBUTION, and the
exemption is substantive rather than convenient. `claude-acp` and `codex-acp` are
pinned to MEASURED adapter generations -- the baked path and `CODEX_CONFIG`
posture section "Built-in ACP node defaults" ratifies literally, and the versions
this factory's sandbox image actually provisions -- so they deliberately differ
from whatever the registry's stable channel has moved on to. They are in the
fixture because the snapshot identity is over the ratified population, not
because the catalog owes them parity.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import builtin_agent_catalog

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SNAPSHOT = _REPO_ROOT / "tests" / "fixtures" / "acp_registry_snapshot"

# The platform a `binary` distribution is rendered for. The registry's binary
# block is keyed by platform target and the factory's sandbox runs Linux on
# x86_64, so this is the one key whose `cmd` describes the filesystem the adapter
# would actually launch on.
_PLATFORM = "linux-x86_64"

# The three entries this suite holds to the registry. The two measured built-ins
# are exempt for the reason the module docstring gives.
_SEEDED_IDS = ("glm-acp-agent", "grok-build", "opencode")


def _document(*, agent_id: str) -> dict[str, Any]:
    """One registry `agent.json`, as committed."""
    decoded: dict[str, Any] = json.loads(
        (_SNAPSHOT / f"{agent_id}.json").read_text(encoding="utf-8")
    )
    return decoded


def _declared_launch(*, document: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    """The `(command, args)` pair one registry distribution renders into.

    `npx` renders as the registry's own `Download/Command` table says --
    `npx <package> [args]` -- with the `-y` the two measured built-in entries
    already carry, so a pinned package needs no interactive install consent. A
    `binary` distribution renders its platform entry's `cmd` and `args`; the
    archive it names is a PROVISIONING step and deliberately has no place in a
    fetch-free launch triple.
    """
    distribution = document["distribution"]
    npx = distribution.get("npx")
    if npx is not None:
        return (f"npx -y {npx['package']}", tuple(npx.get("args", ())))
    platform = distribution["binary"][_PLATFORM]
    return (platform["cmd"], tuple(platform.get("args", ())))


def test_the_registry_snapshot_fixture_holds_every_ratified_agent_id() -> None:
    """The fixture is the committed snapshot, not a partial sample.

    This runs first because every case below is only as good as the population it
    reads: a fixture holding two documents would let a wrong entry pass by simply
    not being measured.
    """
    committed = sorted(path.stem for path in _SNAPSHOT.glob("*.json"))

    assert committed == ["claude-acp", "codex-acp", "glm-acp-agent", "grok-build", "opencode"]


def test_each_seeded_entry_carries_the_registry_pinned_agent_version() -> None:
    """The entry's `version` is the registry's version, not a snapshot date.

    A date passes every refusal and tells a reader nothing about which adapter
    generation the entry describes, which is the half of the pin
    `SPECIFICATION/constraints.md` section "Pinned agent versions" calls a
    measurement receipt.
    """
    catalog = builtin_agent_catalog()

    for agent_id in _SEEDED_IDS:
        assert catalog[agent_id].version == _document(agent_id=agent_id)["version"], agent_id


def test_each_seeded_entry_carries_the_registry_declared_launch_distribution() -> None:
    """The entry's `(command, args)` is what the registry's distribution renders."""
    catalog = builtin_agent_catalog()

    for agent_id in _SEEDED_IDS:
        entry = catalog[agent_id]
        expected = _declared_launch(document=_document(agent_id=agent_id))

        assert (entry.command, entry.args) == expected, agent_id


def test_the_pinned_version_appears_in_a_pinned_package_launch_command() -> None:
    """An `npx` entry pins the version IN the package spec it launches.

    Asserting the `version` field alone would pass for an entry that records
    `1.0.49` beside an unpinned `npx -y @xai-official/grok`, which resolves to
    whatever the registry's channel has moved to -- a pin a reader can see and a
    sandbox does not honour. The binary-distribution entry is excluded because
    its version rides the archive, not the command.
    """
    catalog = builtin_agent_catalog()

    for agent_id in ("glm-acp-agent", "grok-build"):
        entry = catalog[agent_id]

        assert entry.command.endswith(f"@{entry.version}"), (agent_id, entry.command)
