"""The COMMITTED agent and model catalogs, and the snapshot they record.

Binds the first half of `SPECIFICATION/contracts.md` section "Agent and model
catalogs": both catalogs are SNAPSHOTS the plugin ships, they record the
registry snapshot digest and the date they were seeded from, and "the Dispatcher
MUST NOT fetch a registry, a provider, or a catalog service at dispatch time, so
a dispatch depends only on committed bytes".

THE NO-FETCH ASSERTION IS A SOURCE SCAN, and the token choice is the whole
point of it. Asserting that a catalog read "returns the same thing twice" would
pass just as well against a module that fetched and cached, so the
discriminating evidence is that no catalog module can reach a network or
subprocess API AT ALL: the scan looks for the import names that would have to be
present for a fetch to exist (`urllib`, `http`, `socket`, `subprocess`,
`requests`), any one of which is sufficient. A module importing none of them
cannot fetch, whatever its call graph does.

THE DIGEST IS COMPUTED FROM THE SHIPPED BYTES rather than transcribed. A
transcribed literal cannot tell a deliberate re-seed from a silent drift, and
nothing in this sandbox can re-read the upstream registry document to check one
against it. A digest over the catalog's own canonical serialization identifies
the snapshot THIS BUILD carries, which is the property a dispatch needs, and it
cannot fall out of step with the entries it names.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

# The registry agent ids `SPECIFICATION/contracts.md` section "Agent and model
# catalogs" names explicitly. The shipped snapshot must carry every one of them:
# a catalog holding only the two adapters this factory already runs is a catalog
# that cannot route a node to anything new, which is the whole feature.
_RATIFIED_AGENT_IDS = (
    "claude-acp",
    "codex-acp",
    "glm-acp-agent",
    "grok-build",
    "opencode",
)

# Models the specification itself names, so the catalog carries them by
# ratification rather than by this repository's own measurement: the v107
# Claude defaults, the Codex pins, and Scenario 129's provider-qualified
# `zai/glm-5.2`.
_RATIFIED_MODEL_KEYS = (
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-opus-5",
    "openai/gpt-5.5",
    "zai/glm-5.2",
)

# Any one of these import names is sufficient for a fetch to exist. The scan
# reads the source text rather than the module object because an import inside a
# function body is still an import, and a module object shows only what ran.
_FETCH_IMPORTS = ("http", "requests", "socket", "subprocess", "urllib")

_CATALOG_MODULES = (
    "_acp_agent_catalog",
    "_acp_agent_entry",
    "_acp_agent_mechanism",
    "_acp_catalogs",
    "_acp_model_catalog",
    "_acp_model_entry",
)

_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_.]*)", re.MULTILINE)

_SNAPSHOT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _module(*, name: str) -> object:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def test_the_catalog_modules_are_committed_files() -> None:
    """Every catalog module is a committed file under the package tree.

    This is the first assertion on purpose: a catalog that is fetched has no
    file to find, and the whole section's promise is that a dispatch depends
    only on committed bytes.
    """
    for name in _CATALOG_MODULES:
        assert (_COMMANDS / f"{name}.py").is_file(), name


def test_the_shipped_catalogs_record_a_snapshot_digest_and_date() -> None:
    """The snapshot record carries a 64-hex digest and an ISO date."""
    catalogs = _module(name="_acp_catalogs")
    record = catalogs.catalog_snapshot_record()  # pyright: ignore[reportAttributeAccessIssue]

    assert _DIGEST_RE.match(record["agent_catalog_digest"]) is not None, record
    assert _DIGEST_RE.match(record["model_catalog_digest"]) is not None, record
    assert _SNAPSHOT_DATE_RE.match(record["registry_snapshot_date"]) is not None, record


def test_the_snapshot_digest_is_a_function_of_the_shipped_entries() -> None:
    """Two reads agree, and the digest names the entries rather than a constant.

    The agreement half alone would pass against a hard-coded string, so the
    discriminating half is that the digest of the catalog with one entry
    REMOVED differs from the shipped one.
    """
    agents = _module(name="_acp_agent_catalog")
    shipped = agents.agent_catalog_digest(catalog=agents.builtin_agent_catalog())  # pyright: ignore[reportAttributeAccessIssue]
    assert shipped == agents.agent_catalog_digest(catalog=agents.builtin_agent_catalog())  # pyright: ignore[reportAttributeAccessIssue]

    full = dict(agents.builtin_agent_catalog())  # pyright: ignore[reportAttributeAccessIssue]
    del full["claude-acp"]
    assert agents.agent_catalog_digest(catalog=full) != shipped  # pyright: ignore[reportAttributeAccessIssue]


def test_the_agent_catalog_carries_every_ratified_registry_id() -> None:
    """The snapshot names the whole ratified registry population."""
    catalog = _module(name="_acp_agent_catalog").builtin_agent_catalog()  # pyright: ignore[reportAttributeAccessIssue]
    for agent_id in _RATIFIED_AGENT_IDS:
        assert agent_id in catalog, agent_id
        assert catalog[agent_id].agent_id == agent_id
        assert catalog[agent_id].display_name != ""
        assert catalog[agent_id].account_domain != ""
        assert catalog[agent_id].version != ""


def test_the_model_catalog_is_keyed_by_provider_and_model() -> None:
    """Every entry's key is its own `provider/model` pair."""
    catalog = _module(name="_acp_model_catalog").builtin_model_catalog()  # pyright: ignore[reportAttributeAccessIssue]
    for key in _RATIFIED_MODEL_KEYS:
        assert key in catalog, key
    for key, entry in catalog.items():
        assert key == f"{entry.provider}/{entry.model}", key
        assert entry.key == key
        assert entry.display_name != ""
        assert entry.canonical_id != ""


def test_the_claude_and_codex_entries_declare_their_ratified_mechanisms() -> None:
    """`claude-acp` maps through the environment; `codex-acp` through CODEX_CONFIG.

    Both are named literally by `SPECIFICATION/contracts.md` section "Agent and
    model catalogs", so the catalog is wrong rather than merely different if
    either drifts.
    """
    catalog = _module(name="_acp_agent_catalog").builtin_agent_catalog()  # pyright: ignore[reportAttributeAccessIssue]

    claude = catalog["claude-acp"].mechanism
    assert claude.kind == "env"
    assert claude.model == "ANTHROPIC_MODEL"
    assert claude.effort == "CLAUDE_CODE_EFFORT_LEVEL"

    codex = catalog["codex-acp"].mechanism
    assert codex.kind == "json_env"
    assert codex.env == "CODEX_CONFIG"
    assert codex.model == "model"
    assert codex.effort == "model_reasoning_effort"
    assert catalog["codex-acp"].command == "/opt/livespec/codex-acp/bin/codex-acp"


def test_no_catalog_module_can_reach_a_registry_provider_or_catalog_service() -> None:
    """No catalog module imports any API a fetch would need."""
    for name in _CATALOG_MODULES:
        imported = set(_IMPORT_RE.findall((_COMMANDS / f"{name}.py").read_text(encoding="utf-8")))
        roots = {module.partition(".")[0] for module in imported}
        assert roots.isdisjoint(_FETCH_IMPORTS), (name, sorted(roots & set(_FETCH_IMPORTS)))
