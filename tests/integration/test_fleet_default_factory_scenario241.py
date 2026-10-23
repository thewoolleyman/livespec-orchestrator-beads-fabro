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
from livespec_orchestrator_beads_fabro._store_dispatch_claim import claim_stamp_from_record
from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_stamp import (
    stamp_pending_claim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import (
    factory_bin_refusal,
    factory_fabro_bin,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_environment import (
    factory_declaration_refusal,
    factory_environment_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_registry import (
    factory_registry_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import stamp_dispatch_run
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    SECRET_CHANNEL_INLINE_OVERLAY,
    SECRET_CHANNEL_NATIVE_SECRETS,
    SecretChannelRefusal,
    resolve_secret_channel,
)
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
_DISPATCH_ID = "01M5MXVMK95EKAGEV5AX2MFTQJ"
_RUN_ID = "01M580PF02S0VMFKX5HPB05Z8C"

# The registry's own client settings for `petri`. The `bin` is a file each case
# CREATES and marks executable, because the clause requires every validation a
# committed value receives to apply equally to a registry-supplied one — and the
# `bin` grade refuses a path that is not an existing executable, so a spelled
# constant would refuse the very dispatch this case asserts succeeds.
_REGISTRY_BIN_NAME = "registry-fabro"
_HOST_FALLBACK_BIN_NAME = "host-fabro"
_REGISTRY_ENVIRONMENT = "livespec-registry-env"


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


def _executable(*, cwd: Path, name: str) -> str:
    """One real executable file, so a `bin` grade can admit the value naming it.

    The two engine clients a case distinguishes are created rather than spelled,
    for the reason the constants above record: a registry-supplied `bin` is
    graded exactly as a committed one, and the grade asks the filesystem.
    """
    path = cwd / name
    _ = path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def _registry_client(*, cwd: Path) -> dict[str, Any]:
    """The three client settings the registry gives `petri`, with a real `bin`."""
    return {
        "bin": _executable(cwd=cwd, name=_REGISTRY_BIN_NAME),
        "secret_channel": SECRET_CHANNEL_NATIVE_SECRETS,
        "environment": _REGISTRY_ENVIRONMENT,
    }


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


def test_moving_the_fleet_default_reroutes_the_next_fresh_dispatch_with_no_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing only the registry's designation re-routes the next fresh dispatch.

    Both records the clause names are read at EACH designation, because each is
    written by code that resolves the factory for itself and either can keep
    naming the previous one while the resolver has moved on — and the item is
    dispatched to `petri` FIRST, so its own `dispatch_factory` record names the
    old designation when the second dispatch resolves. That is the shape a
    fresh dispatch must ignore: an implementation reading the recorded factory
    as a pin returns `petri` for the second dispatch and satisfies every
    assertion a single-designation case could make.

    The committed file's bytes are compared across the move, which is the one
    assertion distinguishing a fleet default from a re-written configuration.

    Both designations are DECLARED here, which Scenario 241's Background admits
    per case and which is what makes the pin claim able to fail: a recorded
    factory the committed table does not declare is already discarded as
    unusable, so with the Background's undeclared shape a build that read the
    pin on a fresh dispatch would pass this case anyway.
    """
    _write_config(
        cwd=tmp_path,
        factories={
            _LEGACY: {"server": _LEGACY_SERVER},
            _PETRI: {"registry": True},
            _NEXT: {"registry": True},
        },
        default_factory=_FLEET,
    )
    registry = _write_registry(
        cwd=tmp_path, monkeypatch=monkeypatch, payload=_fleet_registry(default=_PETRI)
    )
    _seed_item()
    committed = _config_path(cwd=tmp_path).read_bytes()

    assert _dispatch_records(cwd=tmp_path) == (_PETRI, _PETRI_SERVER, _PETRI, _PETRI_SERVER)

    _ = registry.write_text(json.dumps(_fleet_registry(default=_NEXT)), encoding="utf-8")

    assert _dispatch_records(cwd=tmp_path) == (_NEXT, _NEXT_SERVER, _NEXT, _NEXT_SERVER)
    assert _config_path(cwd=tmp_path).read_bytes() == committed


def _client_settings(*, cwd: Path, factory: str) -> tuple[str, str | None, str]:
    """One factory's EFFECTIVE `bin`, `environment` and `secret_channel`.

    Read through the three production grades rather than off `FactoryTarget`,
    because each is what a dispatch actually consumes and two of them apply a
    layer of their own: `factory_fabro_bin` resolves the entry's declaration
    against the host fallback, and the transport is resolved by a reader that
    never sees a `FactoryTarget` at all — it is asked for the factory by NAME,
    which is what makes it the one of the three that must find the registry on
    its own rather than being handed a resolution.
    """
    target = resolve_fabro_factory(cwd=cwd, factory=factory)
    channel = resolve_secret_channel(block=dispatcher_block(cwd=cwd), factory=factory)
    assert not isinstance(channel, SecretChannelRefusal)
    return (
        factory_fabro_bin(
            factory=target, fallback=_executable(cwd=cwd, name=_HOST_FALLBACK_BIN_NAME)
        ),
        factory_environment_id(factory=target),
        channel,
    )


def _refusals(*, cwd: Path, factory: str) -> tuple[str | None, ...]:
    """Every pre-claim refusal the three client settings and the registry raise."""
    target = resolve_fabro_factory(cwd=cwd, factory=factory)
    return (
        factory_registry_refusal(factory=target),
        factory_bin_refusal(factory=target),
        factory_declaration_refusal(factory=target),
    )


def test_a_registry_backed_entry_declaring_no_client_settings_takes_the_registrys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed entry declaring only `registry` dispatches on the registry's client.

    The committed entry declares NONE of the three, which is the shape the
    clause recommends a fleet member commit, and all three are asserted
    together because they are one question — "how does this Dispatcher speak to
    this factory" — answered from one place, and a per-key case could not tell
    a build that merged two of them from one that merged all three.

    The refusals are asserted EMPTY beside the values, because each key's grade
    runs before the claim and a registry value reaching the field while failing
    its own grade is a dispatch refused for a declaration the repository never
    made.
    """
    _write_config(
        cwd=tmp_path,
        factories={_PETRI: {"registry": True}},
        default_factory=_PETRI,
    )
    _ = _write_registry(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        payload=_fleet_registry(default=_PETRI, client=_registry_client(cwd=tmp_path)),
    )

    assert _client_settings(cwd=tmp_path, factory=_PETRI) == (
        _executable(cwd=tmp_path, name=_REGISTRY_BIN_NAME),
        _REGISTRY_ENVIRONMENT,
        SECRET_CHANNEL_NATIVE_SECRETS,
    )
    assert _refusals(cwd=tmp_path, factory=_PETRI) == (None, None, None)


def test_a_client_key_neither_source_declares_keeps_its_absent_treatment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key declared in neither place is absent, not inherited from elsewhere.

    The control for the case above: without it, an implementation that invented
    a value for every key — the host fallback for `bin`, some default
    environment, a transport — would satisfy every positive assertion there
    while making a repository that declares nothing dispatch differently from
    one that always has. `next` is the registry entry carrying no client keys
    at all, so each reading must be the absent-key answer its own key defines.
    """
    _write_config(
        cwd=tmp_path,
        factories={_NEXT: {"registry": True}},
        default_factory=_NEXT,
    )
    _ = _write_registry(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        payload=_fleet_registry(default=_PETRI, client=_registry_client(cwd=tmp_path)),
    )

    assert _client_settings(cwd=tmp_path, factory=_NEXT) == (
        _executable(cwd=tmp_path, name=_HOST_FALLBACK_BIN_NAME),
        None,
        SECRET_CHANNEL_INLINE_OVERLAY,
    )
    assert _refusals(cwd=tmp_path, factory=_NEXT) == (None, None, None)


def _dispatch_records(*, cwd: Path) -> tuple[str | None, str | None, str | None, str | None]:
    """One fresh dispatch's claim stamp and dispatch-factory record, as four fields.

    Taken together rather than asserted apart because they are two points on ONE
    routing decision and a failure has to say which point dropped it: a stamp
    naming the old designation beside a record naming the new one is a different
    defect from both naming the old one.

    The stamp is read back through the production `claim_stamp_from_record`
    rather than by indexing the metadata, so a case cannot pass by agreeing with
    a nesting the reader does not use — and it is read IMMEDIATELY, before the
    run stamp below replaces it. The clause's subject is the ADMISSION stamp,
    and `stamp_dispatch_run` overwrites that record with the launch's own
    factory: a reading taken afterwards reports the plan's resolution twice and
    cannot fail for an admission stamp that named the wrong factory.
    """
    journal = JournalFile(path=cwd / "journal.jsonl")
    stamp_pending_claim(
        repo=cwd, work_item_id=_WORK_ITEM_ID, dispatch_id=_DISPATCH_ID, journal=journal
    )
    admission = claim_stamp_from_record(record=_fake().show_issue(issue_id=_WORK_ITEM_ID))
    assert admission is not None
    target = resolve_fabro_factory(cwd=cwd)
    _ = stamp_dispatch_run(
        plan=build_plan(
            repo=cwd,
            work_item_id=_WORK_ITEM_ID,
            workflow_toml=cwd / "workflow.toml",
            goal_file=cwd / "goal.md",
            fabro_bin="/opt/fabro",
            fabro_factory_name=target.name,
            fabro_factory_server=target.server,
            janitor=None,
            janitor_checkout=cwd / "janitor",
        ),
        journal=journal,
        run_id=_RUN_ID,
    )
    metadata = _fake().show_issue(issue_id=_WORK_ITEM_ID).get("metadata")
    assert isinstance(metadata, dict)
    recorded = metadata["dispatch_factory"]
    assert isinstance(recorded, dict)
    return (
        admission.factory_name,
        admission.factory_server,
        recorded.get("name"),
        recorded.get("server"),
    )
