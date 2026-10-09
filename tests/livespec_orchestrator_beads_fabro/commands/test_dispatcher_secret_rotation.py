"""A rotated credential takes effect without rebuilding the workflow bundle.

The FOURTH Definition-of-Done assertion of work-item bd-ib-4ipmub. On the
Petri-era engine a workflow version is stored IMMUTABLY on the server, so
"without rewriting the bundle" is not a convenience -- rewriting it means a NEW
version, and a transport that needed one per rotation would make every
credential refresh a redeploy.

Two things have to hold, and they pull in opposite directions, which is why both
are asserted here. The bundle must be INVARIANT under rotation: the vault key is
derived from the environment-variable name alone, so two launches whose
credentials differ produce byte-identical bundles. And the vault must be
RE-WRITTEN on every launch: resolution happens in the worker at consumption
time, so the value the server holds at launch is the value the run uses, and a
transport that stored only on first use would pin every later run to the first
launch's credential.

The third assertion is about EVIDENCE rather than mechanism. Because the bundle
is invariant, two launches are indistinguishable from the bundle alone -- so
whether the second launch actually re-set the vault is unanswerable unless the
dispatch records it. The store is therefore journaled per credential, by vault
key and outcome, and the row carries no value: `SPECIFICATION/contracts.md`
section "Proof credential projection" requires journals and records to carry
names only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_write import (
    write_routed_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    SECRET_CHANNEL_NATIVE_SECRETS,
    VaultSecret,
    vault_secret_name,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_vault import FabroVaultSink

# Two launches' worth of credentials: the SECOND launch's values are the rotated
# ones, and every one of the three differs from its predecessor so a bundle that
# embedded any of them would differ too.
_FIRST = ("rotation-anthropic-1", "rotation-github-1", "rotation-openai-1")
_SECOND = ("rotation-anthropic-2", "rotation-github-2", "rotation-openai-2")

_ENV_NAMES = ("CLAUDE_CODE_OAUTH_TOKEN", "GITHUB_TOKEN", "CODEX_AUTH_JSON")


@dataclass(kw_only=True)
class _RecordingSink:
    """A vault recording the last value stored under each key."""

    stored: dict[str, str] = field(default_factory=dict)

    def set(self, *, secret: VaultSecret) -> str | None:
        self.stored[secret.secret_name] = secret.value
        return None


@dataclass(kw_only=True)
class _StubRunner:
    """A runner that accepts every store and reads nothing."""

    exit_code: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = argv, cwd, timeout_seconds, env, stdin
        return CommandResult(exit_code=self.exit_code, stdout="", stderr="")


@dataclass(kw_only=True)
class _RecordingJournal:
    """An append-only journal capturing every record written to it."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(dict(record))


def _bundle(*, values: tuple[str, str, str]) -> str:
    """One launch's rendered bundle, carrying that launch's three credentials."""
    anthropic, github, openai = values
    return (
        '[workflow]\ngraph = "/abs/workflow.fabro"\n\n'
        "[environments.sandbox.env]\n"
        f"CLAUDE_CODE_OAUTH_TOKEN = {json.dumps(anthropic)}\n"
        f"GITHUB_TOKEN = {json.dumps(github)}\n"
        f"CODEX_AUTH_JSON = {json.dumps(openai)}\n"
    )


def test_the_sink_can_record_what_it_stored() -> None:
    """The store is journalable, which is the only way a rotation is observable.

    Asserted as a field question because it is the precondition for the
    evidence assertion below: with no journal seam the second launch's store
    leaves no trace, and the bundle -- correctly -- looks identical either way.
    """
    assert "journal" in {field_.name for field_ in fields(FabroVaultSink)}


def test_two_launches_with_rotated_credentials_write_identical_bundles(
    tmp_path: Path,
) -> None:
    """The bundle is invariant under rotation, so the server needs no new version."""
    first = tmp_path / "first.toml"
    second = tmp_path / "second.toml"
    sink = _RecordingSink()
    for overlay, values in ((first, _FIRST), (second, _SECOND)):
        assert (
            write_routed_overlay(
                overlay=overlay,
                rendered=_bundle(values=values),
                channel=SECRET_CHANNEL_NATIVE_SECRETS,
                proof_credentials_env="",
                sink=sink,
            )
            is None
        )
    assert first.read_bytes() == second.read_bytes()


def test_the_second_launch_leaves_the_rotated_value_in_the_vault(tmp_path: Path) -> None:
    """Every launch re-writes the vault, so the newest credential is what runs."""
    sink = _RecordingSink()
    for values in (_FIRST, _SECOND):
        _ = write_routed_overlay(
            overlay=tmp_path / "overlay.toml",
            rendered=_bundle(values=values),
            channel=SECRET_CHANNEL_NATIVE_SECRETS,
            proof_credentials_env="",
            sink=sink,
        )
    assert sink.stored == {
        vault_secret_name(env_name="CLAUDE_CODE_OAUTH_TOKEN"): _SECOND[0],
        vault_secret_name(env_name="GITHUB_TOKEN"): _SECOND[1],
        vault_secret_name(env_name="CODEX_AUTH_JSON"): _SECOND[2],
    }


def test_each_store_is_journaled_by_vault_key_and_outcome() -> None:
    """The record names the key and says whether it was stored; never the value."""
    journal = _RecordingJournal()
    sink = FabroVaultSink(
        fabro_bin="/usr/local/bin/fabro",
        server_url="https://hp-xubuntu.example.invalid:32278",
        runner=_StubRunner(),
        cwd=Path("/workspace/repo"),
        journal=journal,
    )
    for env_name, value in zip(_ENV_NAMES, _SECOND, strict=True):
        assert (
            sink.set(
                secret=VaultSecret(
                    env_name=env_name,
                    secret_name=vault_secret_name(env_name=env_name),
                    value=value,
                )
            )
            is None
        )
    keys = [record.get("secret") for record in journal.records]
    assert keys == [vault_secret_name(env_name=name) for name in _ENV_NAMES]
    assert {record.get("outcome") for record in journal.records} == {"stored"}
    rendered = json.dumps(journal.records)
    for value in _SECOND:
        assert value not in rendered


def test_a_refused_store_is_journaled_as_refused() -> None:
    """A rotation that did NOT take effect says so, rather than leaving a gap.

    An absent row and a `stored` row are both readable; an absent row for a
    FAILED store is the one state that reads as "this launch never tried",
    which is exactly the wrong conclusion when the vault still holds the
    previous launch's credential.
    """
    journal = _RecordingJournal()
    sink = FabroVaultSink(
        fabro_bin="/usr/local/bin/fabro",
        server_url=None,
        runner=_StubRunner(exit_code=1),
        cwd=Path("/workspace/repo"),
        journal=journal,
    )
    secret = VaultSecret(
        env_name="GITHUB_TOKEN",
        secret_name=vault_secret_name(env_name="GITHUB_TOKEN"),
        value=_SECOND[1],
    )
    assert sink.set(secret=secret) is not None
    assert [record.get("outcome") for record in journal.records] == ["refused"]
    assert _SECOND[1] not in json.dumps(journal.records)
