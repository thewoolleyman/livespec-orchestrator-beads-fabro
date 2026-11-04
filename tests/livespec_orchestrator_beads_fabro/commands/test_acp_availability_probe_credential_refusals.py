"""The refusals and degraded readings of the confirmation turn's credential projection.

Beside `test_acp_availability_probe_credential.py`, which binds the projection
itself. Every case here is a state in which a probe would otherwise be launched
with a credential it could not deliver, or would hide the reason it could not be
launched at all. A refusal is the clause's "any other probe failure": the
candidate is skipped for this evaluation, no hold is minted, and the message
names the cause without ever carrying the credential value.

A SEPARATE module because these arms were found by a coverage measurement taken
after the first module's Red was authored, and a Red's test bytes are fixed
across its Red-to-Green pair.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_SERVER = "https://gmktec.example.ts.net:32276"
_TOKEN = "sk-probe-token-refusals"


def _config(*, channel: str) -> str:
    entry = {"server": _SERVER, "environment": "livespec-ci", "secret_channel": channel}
    return json.dumps(
        {
            "livespec-orchestrator-beads-fabro": {
                "dispatcher": {"default_factory": "petri", "factories": {"petri": entry}}
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
    secret_exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

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
        _ = (cwd, timeout_seconds, env, stdin)
        return _Command(exit_code=self.secret_exit_code, stdout="", stderr=f"echoed {_TOKEN}")

    def launched(self) -> bool:
        """Whether anything other than a vault store was spent on the engine."""
        return any("secret" not in argv for argv in self.calls)


def _probe(*, tmp_path: Path, channel: str, engine: _Engine) -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    candidate = schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="claude-code-acp"),
        identity=schema.AcpCandidateIdentity(
            display_name="Claude Opus 5",
            candidate_key="claude-opus-5-high",
            availability_key="anthropic",
        ),
    )
    _ = (tmp_path / ".livespec.jsonc").write_text(_config(channel=channel), encoding="utf-8")
    runner = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_run")
    return runner.run_availability_probe(
        repo=tmp_path,
        candidate=candidate,
        builtin=True,
        work_item_id="bd-ib-3pfauo",
        observation_ids=(),
        now_iso="2026-10-29T09:15:00Z",
        timeout_seconds=120,
        runner=engine,
    )


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A HOME with no caam record, a lock root of the test's own, and one unnumbered token."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    vault = importlib.import_module(f"{_PACKAGE}._dispatcher_secret_vault")
    monkeypatch.setattr(vault, "_LAUNCH_LOCK_ROOT", tmp_path / "vault-locks")


def test_an_unrecognised_secret_channel_refuses_the_turn_before_any_run(tmp_path: Path) -> None:
    """The factory's own declaration is graded exactly as a dispatch grades it."""
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, channel="carrier_pigeon", engine=engine)

    assert isinstance(result, str), result
    assert "carrier_pigeon" in result
    assert engine.launched() is False


def test_a_vault_that_will_not_take_the_credential_refuses_without_echoing_it(
    tmp_path: Path,
) -> None:
    """A stale or absent vault entry would authenticate nothing, so no run is launched."""
    engine = _Engine(secret_exit_code=1)

    result = _probe(tmp_path=tmp_path, channel="native_secrets", engine=engine)

    assert isinstance(result, str), result
    assert "LIVESPEC_DISPATCH_CLAUDE_CODE_OAUTH_TOKEN" in result
    assert _TOKEN not in result
    assert engine.launched() is False


def test_a_routing_the_bundle_cannot_carry_refuses_the_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The routing's own refusal is surfaced rather than launched past."""
    credential = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_credential")
    channel = importlib.import_module(f"{_PACKAGE}._dispatcher_secret_channel")
    refusal = channel.SecretChannelRefusal(message="the bundle and the name list disagree")

    def _refused(**_: object) -> object:
        return refusal

    monkeypatch.setattr(credential, "route_secrets_through_vault", _refused)
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, channel="native_secrets", engine=engine)

    assert result == "the bundle and the name list disagree"
    assert engine.launched() is False
