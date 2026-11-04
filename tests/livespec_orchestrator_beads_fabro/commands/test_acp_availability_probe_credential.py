"""The projected worker credential one confirmation turn carries.

Beside `test_acp_availability_probe_run_environment.py`, which binds WHERE the
turn runs. This module binds WHAT IT AUTHENTICATES WITH. The clause confirms
availability only through "a successfully completed ACP prompt turn using the
candidate's pinned adapter version, requested model and effort, and projected
worker credential identity", and a turn placed in the factory's environment but
launched with no credential in it cannot authenticate, so no healthy provider
can ever earn a confirmation and the post-expiry stall persists unchanged.

THE CREDENTIAL IS THE DISPATCH'S OWN, SELECTED BY THE SAME FUNCTION. The expected
value is the token `select_factory_credential` names, including the caam
rotation's pool slot, so a probe resolving its own copy of the choice would pass
only for as long as nobody changed the shared selection.

THE TRANSPORT IS THE FACTORY'S DECLARED ONE. On the inline channel the value
rides the mode-agnostic manifest the engine reads; on the native channel it is
stored in the factory vault BEFORE the launch and the manifest carries only the
reference, because a Petri-era server persists a manifest in an immutable
workflow version and an inline credential there is the exposure that transport
exists to close.

THE CONTROLS ARE NOT OPTIONAL. A probe that projected the Claude credential for
every candidate would hand it to an adapter that never asked for it, and one
that held the factory vault lock past the turn would block the next dispatch to
the same factory for as long as the process lives.
"""

from __future__ import annotations

import fcntl
import importlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_RUN_ID = "01M5PROBECRED000000000000"
_NOW = "2026-10-29T09:15:00Z"
_SERVER = "https://gmktec.example.ts.net:32276"
_ENVIRONMENT = "livespec-ci"
_TOKEN = "sk-probe-token-unnumbered"
_SLOT_TOKEN = "sk-probe-token-pool-slot"
_VAULT_NAME = "LIVESPEC_DISPATCH_CLAUDE_CODE_OAUTH_TOKEN"


def _config(*, environment: str | None = None, native: bool = False) -> str:
    entry: dict[str, str] = {"server": _SERVER}
    if environment is not None:
        entry["environment"] = environment
    if native:
        entry["secret_channel"] = "native_secrets"
    return json.dumps(
        {
            "livespec-orchestrator-beads-fabro": {
                "dispatcher": {
                    "default_factory": "petri",
                    "factories": {"petri": entry},
                }
            }
        }
    )


@dataclass(kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Engine:
    """A fabro runner that records every argv, the manifest it launched, and each stored secret."""

    calls: list[list[str]] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    stored: list[tuple[str, str]] = field(default_factory=list)
    order: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> _Command:
        self.calls.append(list(argv))
        _ = (cwd, timeout_seconds, env)
        if "--version" in argv:
            return _Command(exit_code=0, stdout="fabro 0.254.0 (8869e88 2026-10-01)\n")
        if "secret" in argv:
            assert stdin is not None
            self.order.append("secret")
            self.stored.append((argv[argv.index("set") + 1], os.pread(stdin, 4096, 0).decode()))
            return _Command(exit_code=0, stdout="")
        if "inspect" in argv:
            return _Command(exit_code=0, stdout=json.dumps([self._record()]))
        if "events" in argv:
            return _Command(exit_code=0, stdout="[]")
        self.order.append("run")
        self.manifests.append(Path(argv[argv.index("run") + 1]).read_text(encoding="utf-8"))
        return _Command(exit_code=0, stdout=f"Run: {_RUN_ID}\n")

    def _record(self) -> dict[str, Any]:
        return {
            "run_id": _RUN_ID,
            "status": {"kind": "succeeded"},
            "stages": {"confirm@1": {"state": "succeeded"}},
        }


def _candidate(*, availability_key: str = "anthropic") -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="claude-code-acp"),
        identity=schema.AcpCandidateIdentity(
            display_name="Claude Opus 5",
            candidate_key="claude-opus-5-high",
            availability_key=availability_key,
        ),
    )


def _probe(
    *, tmp_path: Path, config: str, engine: _Engine, builtin: bool = True, candidate: Any = None
) -> Any:
    _ = (tmp_path / ".livespec.jsonc").write_text(config, encoding="utf-8")
    runner = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_run")
    return runner.run_availability_probe(
        repo=tmp_path,
        candidate=_candidate() if candidate is None else candidate,
        builtin=builtin,
        work_item_id="bd-ib-3pfauo",
        observation_ids=("acpobs-f2987ee775375454124951e3",),
        now_iso=_NOW,
        timeout_seconds=120,
        runner=engine,
    )


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME with no caam record and a vault lock root of the test's own."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    vault = importlib.import_module(f"{_PACKAGE}._dispatcher_secret_vault")
    monkeypatch.setattr(vault, "_LAUNCH_LOCK_ROOT", tmp_path / "vault-locks")
    return home


def test_the_inline_channel_carries_the_selected_credential_in_the_factory_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The turn authenticates with the credential a dispatch would project."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, config=_config(environment=_ENVIRONMENT), engine=engine)

    assert not isinstance(result, str), result
    (manifest,) = engine.manifests
    assert f"[environments.{_ENVIRONMENT}.env]" in manifest, manifest
    assert f"CLAUDE_CODE_OAUTH_TOKEN = {json.dumps(_TOKEN)}" in manifest, manifest
    assert engine.stored == [], "the inline channel stores nothing in the vault"


def test_the_credential_is_the_one_the_dispatch_selector_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    """The caam pool slot wins exactly as it does for a dispatch, under the standard name."""
    selector = importlib.import_module(f"{_PACKAGE}._dispatcher_factory_account_selector")
    record = selector.selected_account_record_path(home=isolated_home)
    record.parent.mkdir(parents=True)
    _ = record.write_text(json.dumps({"profile": "anthropic-3"}), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3", _SLOT_TOKEN)
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, config=_config(environment=_ENVIRONMENT), engine=engine)

    assert not isinstance(result, str), result
    (manifest,) = engine.manifests
    assert f"CLAUDE_CODE_OAUTH_TOKEN = {json.dumps(_SLOT_TOKEN)}" in manifest, manifest
    assert _TOKEN not in manifest, manifest


def test_the_native_channel_stores_the_credential_before_launch_and_names_only_a_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The vault holds the value, the manifest holds the reference, and the order is store-first."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    engine = _Engine()
    config = _config(environment=_ENVIRONMENT, native=True)

    result = _probe(tmp_path=tmp_path, config=config, engine=engine)

    assert not isinstance(result, str), result
    assert engine.stored == [(_VAULT_NAME, _TOKEN)]
    assert engine.order == ["secret", "run"]
    (manifest,) = engine.manifests
    assert "{{ secrets." + _VAULT_NAME + " }}" in manifest, manifest
    assert _TOKEN not in manifest, manifest
    assert all(_TOKEN not in " ".join(argv) for argv in engine.calls), engine.calls


def test_the_vault_launch_lock_is_released_when_the_turn_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A probe that kept the factory lock would block the next dispatch to that factory."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    config = _config(environment=_ENVIRONMENT, native=True)

    result = _probe(tmp_path=tmp_path, config=config, engine=_Engine())

    assert not isinstance(result, str), result
    (lock,) = list((tmp_path / "vault-locks").glob("*.lock"))
    with lock.open("r+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_a_healthy_candidate_with_the_credential_records_a_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A completed turn that carried the credential confirms, and the row says so."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, config=_config(environment=_ENVIRONMENT), engine=engine)

    assert not isinstance(result, str), result
    assert f"CLAUDE_CODE_OAUTH_TOKEN = {json.dumps(_TOKEN)}" in engine.manifests[0]
    assert result.confirmed is True
    assert result.journal_record["confirmed"] is True
    assert result.journal_record["outcome"] == "turn-completed"
    assert result.journal_record["satisfies_observation_ids"] == ["acpobs-f2987ee775375454124951e3"]


def test_a_candidate_that_is_not_claude_is_handed_no_claude_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the credential belongs to the Claude adapter, not to every probe."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    engine = _Engine()

    result = _probe(
        tmp_path=tmp_path,
        config=_config(environment=_ENVIRONMENT, native=True),
        engine=engine,
        builtin=False,
        candidate=_candidate(availability_key="openai"),
    )

    assert not isinstance(result, str), result
    assert engine.stored == []
    assert _TOKEN not in engine.manifests[0], engine.manifests[0]
    assert "[environments." not in engine.manifests[0], engine.manifests[0]


def test_a_credential_with_no_environment_to_key_it_under_refuses_the_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine reads an env table only under the selected environment, so none is a refusal."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, config=_config(), engine=engine)

    assert isinstance(result, str), result
    assert "environment" in result
    assert engine.manifests == [], "no run was launched for a turn that could not authenticate"
