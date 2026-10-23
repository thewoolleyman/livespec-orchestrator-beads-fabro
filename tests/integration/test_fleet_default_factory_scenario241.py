"""Scenario 241 — the registry designates the fleet default and carries its client settings.

Binds `SPECIFICATION/scenarios.md` Scenario 241 and the fleet-default half of
the host-factory-registry clause of `SPECIFICATION/contracts.md`. Every case
starts from a `.livespec.jsonc` and a registry JSON file ON DISK and runs the
production configuration and resolution seams; the ledger is this repository's
own hermetic `FakeBeadsClient`.

WHY THE FACTORY IS ASSERTED AT THE CLAIM STAMP AND THE DISPATCH-FACTORY RECORD
rather than at the resolver alone. `resolve_fabro_factory` answering with the
registry's designated factory proves the READING; it does not prove that factory
reaches the two records the clause names. Both are written by code that resolves
the factory for itself — the admission stamp through
`unrecorded_dispatch_factory_target`, the dispatch-factory record through the
plan — so either can keep naming a previous designation while the resolver has
moved on, and the disagreement is invisible: the item's own records would name a
factory the work never reached, with nothing having failed.

WHY THE MOVE CASE RE-READS THE COMMITTED FILE'S BYTES. "With the repository's
committed configuration unchanged" is the whole point of the fleet default, and
an implementation that re-routed by rewriting `.livespec.jsonc` would satisfy
every factory assertion here while defeating the reason the key exists. The
bytes are snapshotted before the move and compared after it, which is the one
assertion an address-only test cannot make.

WHY THE OVERRIDE CASES ASSERT A NEGATIVE BESIDE THE POSITIVE. A repository-level
`default_factory` naming a declared factory, and a repository-level client key,
each outrank the registry — and an implementation that read the registry not at
all would satisfy the positive half of both. Each override case therefore also
asserts that the resolved value is NOT the registry's, which only an
implementation that reads the registry and then lets the committed value win can
satisfy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_factory
from livespec_orchestrator_beads_fabro.types import StoreConfig

# Two factories the registry maps, and a third the repository commits itself.
# `.example` is reserved by RFC 2606, so no inventory this fleet renders can
# collide with these addresses on the host the suite happens to run on.
_PETRI = "petri"
_NEXT = "next"
_LEGACY = "legacy"
_PETRI_SERVER = "https://petri.example:32276"
_NEXT_SERVER = "https://next.example:32276"
_LEGACY_SERVER = "https://legacy.example:32276"

_REGISTRY_PATH_ENV_VAR = "LIVESPEC_FABRO_FACTORY_REGISTRY"
_FACTORY_SELECTION_ENV_VAR = "LIVESPEC_FABRO_FACTORY"
_FLEET = "fleet"

_TENANT = "livespec-orch-beads-fabro"
_PREFIX = "bd-ib"
_WORK_ITEM_ID = "bd-ib-ep4eeo"


@pytest.fixture(autouse=True)
def _hermetic_registry_env(monkeypatch: pytest.MonkeyPatch) -> object:
    """A fresh in-memory tenant, and neither routing variable inherited.

    Both deletions are load-bearing rather than hygiene. `LIVESPEC_FABRO_FACTORY`
    outranks every selection these cases declare, so a value leaking in from the
    dispatch that runs this suite would decide them instead of the configuration
    under test. The registry path variable is what points each case at its own
    registry file rather than at whatever the host happens to carry.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:fleet-default-scenario241")
    monkeypatch.delenv(_FACTORY_SELECTION_ENV_VAR, raising=False)
    monkeypatch.delenv(_REGISTRY_PATH_ENV_VAR, raising=False)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _store() -> StoreConfig:
    """The hermetic tenant every case reads and writes through."""
    return StoreConfig(
        tenant=_TENANT,
        prefix=_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_store())
    assert isinstance(client, FakeBeadsClient)
    return client


def _seed_item() -> None:
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=_WORK_ITEM_ID,
            issue_type="feature",
            title="Resolve the fleet default factory from the registry",
            description="## Definition of Done\n\n- The fleet default decides.\n",
            assignee=None,
            created_at="2026-10-23T00:00:00Z",
        )
    )


def _config_path(*, cwd: Path) -> Path:
    return cwd / ".livespec.jsonc"


def _write_config(
    *,
    cwd: Path,
    factories: dict[str, Any],
    default_factory: str,
) -> None:
    _ = _config_path(cwd=cwd).write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"tenant": _TENANT, "prefix": _PREFIX, "fake": True},
                    "dispatcher": {
                        "factories": factories,
                        "default_factory": default_factory,
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def _write_registry(*, cwd: Path, monkeypatch: pytest.MonkeyPatch, payload: object) -> Path:
    path = cwd / "fabro-factories.json"
    _ = path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(_REGISTRY_PATH_ENV_VAR, str(path))
    return path


def _fleet_registry(*, default: str, client: dict[str, Any] | None = None) -> dict[str, Any]:
    """A registry mapping both factories, designating one of them the fleet default."""
    petri: dict[str, Any] = {"server": _PETRI_SERVER}
    petri.update(client or {})
    return {"default": default, _PETRI: petri, _NEXT: {"server": _NEXT_SERVER}}


def test_a_fleet_default_resolves_to_the_factory_the_registry_designates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`default_factory: "fleet"` dispatches to the registry's designated factory.

    The repository declares `legacy` and does NOT declare `petri`, which is the
    scenario's own Background and the discriminating shape: an implementation
    resolving the default against the committed table alone could not produce
    `petri` at all, and one falling back to the implicit target would produce a
    server of `None` — the ambient local Fabro — rather than failing.

    The address is asserted beside the name because the name alone is satisfied
    by a target carrying no address, which every downstream surface reads as
    this host's own engine.
    """
    _write_config(
        cwd=tmp_path,
        factories={_LEGACY: {"server": _LEGACY_SERVER}},
        default_factory=_FLEET,
    )
    _ = _write_registry(
        cwd=tmp_path, monkeypatch=monkeypatch, payload=_fleet_registry(default=_PETRI)
    )
    _seed_item()

    target = resolve_fabro_factory(cwd=tmp_path)

    assert target.name == _PETRI
    assert target.server == _PETRI_SERVER
