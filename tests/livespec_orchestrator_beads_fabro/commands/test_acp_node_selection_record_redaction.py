"""The per-node selection record carries REDACTED STRUCTURAL FIELDS ONLY.

Binds the redaction requirement the "Per-node selection" paragraph of
`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" places on the record: it is built from redacted structural fields, so
no adapter byte reaches the journal.

WHAT THIS IS NOT, STATED FIRST BECAUSE IT IS THE OBVIOUS WRONG READING. This is
NOT a secret-redaction mechanism, and writing it as one would misdescribe the
contract. A fallback-enabled candidate's `command`, `args` and `env` are
COMMITTED PUBLIC DATA -- `_acp_node_repository` refuses an `env` key that so
much as reads like a credential, saying in as many words that credentials must
arrive through the Worker credential projection -- so by the time a chain
resolves there is no secret in an adapter to leak. The needles below are
therefore ordinary public markers, not pretend tokens.

WHAT THE REQUIREMENT ACTUALLY BUYS, which is why it is still worth asserting.
The record's job is to let a reader reconstruct WHICH candidate ran and why, and
every field it carries for that purpose is an opaque key, an index or a digest.
Adapter bytes are the one kind of content that would make the record unstable:
they change whenever a command, an argument or a base URL moves, so a record
carrying them would differ between two dispatches that made the IDENTICAL
choice, and the digests sitting beside them -- whose whole value is that equal
digests mean equal chains -- would be the only trustworthy fields left. The
journal already keeps adapter content behind the separate `redacted` projection
for the resolution record; this asserts the newest writer into that journal
observes the same discipline, and it is handed the whole `AcpCandidate`, adapter
included, so nothing but its own field list keeps the adapter out.

THE ABSENCES ARE ASSERTED AGAINST A FIXTURE THAT GENUINELY CARRIES THEM, which
is what separates this from a test that would pass against any record at all.
Every needle is a value this chain really declares -- the primary's command, its
argument, its environment NAME and its environment VALUE, and the same four for
the fallback -- and a sibling case reads them back off the resolved adapters, so
a fixture that stopped declaring them turns this file red instead of quietly
making it vacuous. The positive half is asserted too, because a projection that
emitted an empty record would satisfy every absence perfectly.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NODE = "implement"
_ITEM = "bd-ib-wvj4rk"

_PRIMARY_DOMAIN = "primarydomain"
_PRIMARY_KEY = "primarymodel"
_FALLBACK_DOMAIN = "fallbackdomain"
_FALLBACK_KEY = "fallbackmodel"

# The adapter bytes this chain declares. Each is a DISTINCTIVE literal so a hit
# anywhere in the serialized record is unambiguous, and each is a different KIND
# of adapter content: the command, an argument, an environment name and an
# environment value. A projection leaking any one of them leaks the shape.
#
# Every name here is deliberately ORDINARY PUBLIC CONFIGURATION. The repository
# reader refuses a credential-shaped `env` key outright, so a fixture reaching
# for `..._SECRET_TOKEN` does not test redaction -- it fails to resolve at all.
_PRIMARY_COMMAND = "primary-acp-executable"
_PRIMARY_ARG = "--primary-arg-marker"
_PRIMARY_ENV_NAME = "PRIMARY_BASE_URL"
_PRIMARY_ENV_VALUE = "https://primary-marker-9f3c.example"
_FALLBACK_COMMAND = "fallback-acp-executable"
_FALLBACK_ARG = "--fallback-arg-marker"
_FALLBACK_ENV_NAME = "FALLBACK_BASE_URL"
_FALLBACK_ENV_VALUE = "https://fallback-marker-2b7d.example"

_ADAPTER_BYTES = (
    _PRIMARY_COMMAND,
    _PRIMARY_ARG,
    _PRIMARY_ENV_NAME,
    _PRIMARY_ENV_VALUE,
    _FALLBACK_COMMAND,
    _FALLBACK_ARG,
    _FALLBACK_ENV_NAME,
    _FALLBACK_ENV_VALUE,
)

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "npx -y claude-acp"
review_adapter = "npx -y claude-acp"

[run.environment]
id = "livespec-ci"
"""

_WORKFLOW_GRAPH = """digraph implement {
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="{{ inputs.implement_adapter }}", timeout="60s"]
    review    [backend="acp", acp.command="{{ inputs.review_adapter }}", timeout="60s"]
    start -> implement
    implement -> review
    review -> exit
}
"""


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


class _RecordingJournal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _primary() -> dict[str, Any]:
    return {
        "display_name": "Primary adapter",
        "candidate_key": _PRIMARY_KEY,
        "availability_key": _PRIMARY_DOMAIN,
        "command": _PRIMARY_COMMAND,
        "args": [_PRIMARY_ARG],
        "env": {_PRIMARY_ENV_NAME: _PRIMARY_ENV_VALUE},
    }


def _fallback() -> dict[str, Any]:
    return {
        "display_name": "Fallback adapter",
        "candidate_key": _FALLBACK_KEY,
        "availability_key": _FALLBACK_DOMAIN,
        "command": _FALLBACK_COMMAND,
        "args": [_FALLBACK_ARG],
        "env": {_FALLBACK_ENV_NAME: _FALLBACK_ENV_VALUE},
    }


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_WORKFLOW_GRAPH, encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Operator",
                    "operator_email": "operator@example.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "acp_nodes": {
                            _NODE: {**_primary(), "fallbacks": [_fallback()]},
                            # Its OWN availability domain: `review` shares the
                            # primary's otherwise, so the hold below would empty
                            # its single-candidate chain and refuse the dispatch
                            # before any record was written.
                            "review": {
                                **_primary(),
                                "availability_key": "reviewdomain",
                                "candidate_key": "reviewmodel",
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return repo


def _domain_hold(*, hold_key: str) -> Any:
    records = _module(name="_acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id="acp-obs-0123456789abcdef",
        scope="availability-domain",
        hold_key=hold_key,
        candidate_key=None,
        cause="quota",
        occurred_at="2026-10-16T10:00:00Z",
        expires_at="2026-10-16T22:00:00Z",
    )


def _selection_record(*, repo: Path, holds: tuple[Any, ...]) -> dict[str, Any]:
    """The ONE selection record this dispatch journals."""
    sources = _module(name="_dispatcher_acp_chain_sources")
    catalogs_module = _module(name="_acp_catalogs")
    repository = _module(name="_acp_node_repository")
    ledger_module = _module(name="_acp_hold_ledger")
    preflight = _module(name="_acp_candidate_preflight")
    verdicts = _module(name="_acp_preflight_verdict")
    nodes = _module(name="_dispatcher_acp_nodes")
    selection = _module(name="_acp_node_selection")

    block = sources.workflow_scoped_dispatcher_block(repo=repo)
    catalogs = catalogs_module.resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    declared = repository.repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolved = sources.repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    assert not isinstance(resolved, str), resolved
    chains, graph_text, builtin_pairs = resolved
    verdict = verdicts.build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=ledger_module.AcpHoldLedger(
            holds=holds, unobservable=(), observation_ids=frozenset()
        ),
        inputs=preflight.PreflightInputs(holds=holds, builtin_pairs=builtin_pairs),
    )
    journal = _RecordingJournal()
    resolution = nodes.prepare_acp_nodes(
        repo=repo,
        committed=repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml",
        overrides=(),
        journal=journal,
        work_item_id=_ITEM,
        verdict=verdict,
    )
    assert not isinstance(resolution, str), resolution
    matching = [
        record
        for record in journal.records
        if record.get("stage") == selection.ACP_NODE_SELECTION_STAGE
    ]
    assert len(matching) == 1, journal.records
    return matching[0]


def test_the_record_carries_no_adapter_command_argument_or_environment_byte(
    tmp_path: Path,
) -> None:
    """No adapter byte of EITHER candidate reaches the journal.

    The record is searched as SERIALIZED JSON rather than field by field,
    because a leak is only interesting if it reaches the journal and a field
    walk would have to anticipate which key the adapter arrived under -- which
    is exactly what a new field added later would defeat.
    """
    repo = _repo(tmp_path=tmp_path)

    record = _selection_record(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))
    serialized = json.dumps(record)

    for needle in _ADAPTER_BYTES:
        assert needle not in serialized, (needle, serialized)


def test_the_fixture_really_carried_those_bytes_into_the_resolved_adapters(
    tmp_path: Path,
) -> None:
    """The CONTROL for the case above, without which it proves nothing.

    Every absence asserted there is evidence of redaction only if the chain this
    dispatch resolved genuinely carried the bytes. Read off the resolved
    adapters -- the value the selection record's own projection is handed -- so
    a fixture that silently stopped declaring an `env` table, or a resolution
    that dropped it, turns this case red instead of quietly making the other one
    vacuous.
    """
    repo = _repo(tmp_path=tmp_path)
    sources = _module(name="_dispatcher_acp_chain_sources")
    catalogs_module = _module(name="_acp_catalogs")
    repository = _module(name="_acp_node_repository")

    block = sources.workflow_scoped_dispatcher_block(repo=repo)
    catalogs = catalogs_module.resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    declared = repository.repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolved = sources.repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    assert not isinstance(resolved, str), resolved
    chains, _graph_text, _builtin_pairs = resolved
    chain = chains[_NODE]

    rendered = json.dumps(
        [
            {
                "command": one.adapter.command,
                "args": list(one.adapter.args),
                "env": dict(one.adapter.env),
            }
            for one in (chain.primary, *chain.fallbacks)
        ]
    )
    for needle in _ADAPTER_BYTES:
        assert needle in rendered, (needle, rendered)


def test_the_record_still_carries_every_structural_field_the_clause_requires(
    tmp_path: Path,
) -> None:
    """The positive half: redaction is not achieved by emitting nothing.

    A projection that dropped its fields would satisfy every absence above
    perfectly, so the fields the clause DOES require are asserted populated in
    the same breath -- including the skip that moved the selection, which is the
    field most likely to be sacrificed to make a redaction test pass.
    """
    repo = _repo(tmp_path=tmp_path)

    record = _selection_record(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))

    selections: Any = record["selections"]
    chosen = selections[_NODE]
    assert chosen["selected_index"] == 1
    assert chosen["selected_availability_key"] == _FALLBACK_DOMAIN
    assert chosen["selected_candidate_key"] == _FALLBACK_KEY
    assert chosen["selection_identity"]
    assert chosen["primary_generation_digest"]
    assert chosen["full_chain_digest"]
    # The skipped primary is named by its OPAQUE KEYS, which is what "redacted
    # structural fields" means here: the candidate is identifiable for triage
    # without its adapter travelling along.
    assert chosen["holds"] == [
        {
            "availability_key": _PRIMARY_DOMAIN,
            "candidate_key": _PRIMARY_KEY,
            "reason": "typed-availability-hold",
            "cause": "quota",
            "scope": "availability-domain",
            "hold_key": _PRIMARY_DOMAIN,
        }
    ]
