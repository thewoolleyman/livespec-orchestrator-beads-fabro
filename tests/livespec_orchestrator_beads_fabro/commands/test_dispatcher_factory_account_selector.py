"""Tests for the caam-published factory credential slot selector."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    SELECTED_ACCOUNT_RECORD_REL,
    FactoryCredentialChoice,
    factory_credential_env_name,
    parse_selected_profile,
    read_selected_profile,
    resolve_factory_credential_env_name,
    select_factory_credential,
    selected_account_record_path,
)

_SLOT = "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3"


def _write_record(*, home: Path, payload: object) -> None:
    path = selected_account_record_path(home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def test_record_path_is_the_fixed_writer_location() -> None:
    home = Path("/home/someone")
    assert selected_account_record_path(home=home) == home / SELECTED_ACCOUNT_RECORD_REL
    assert (
        Path(".local/state/caam-usage-rotate/selected-account.json") == SELECTED_ACCOUNT_RECORD_REL
    )


@pytest.mark.parametrize(
    ("record_text", "expected"),
    [
        ('{"account_uuid": "u", "profile": "anthropic-3", "written_at": "t"}', "anthropic-3"),
        ('{"profile": "  anthropic-1  "}', "anthropic-1"),
        ("not json at all", None),
        ("[1, 2, 3]", None),
        ('{"account_uuid": "u"}', None),
        ('{"profile": 3}', None),
        ('{"profile": ""}', None),
        ('{"profile": "   "}', None),
    ],
)
def test_parse_selected_profile_is_tolerant(*, record_text: str, expected: str | None) -> None:
    assert parse_selected_profile(record_text=record_text) == expected


def test_resolve_prefers_the_slot_when_present() -> None:
    choice = resolve_factory_credential_env_name(
        selected_profile="anthropic-3",
        available_env_names=frozenset({_SLOT, CLAUDE_OAUTH_TOKEN_ENV}),
    )
    assert choice == FactoryCredentialChoice(env_name=_SLOT, fallback_reason=None)


def test_resolve_normalizes_hyphen_and_case_into_the_slot_name() -> None:
    choice = resolve_factory_credential_env_name(
        selected_profile="anthropic-3",
        available_env_names=frozenset({_SLOT}),
    )
    assert choice.env_name == _SLOT


def test_resolve_falls_back_when_no_profile() -> None:
    choice = resolve_factory_credential_env_name(
        selected_profile=None,
        available_env_names=frozenset({CLAUDE_OAUTH_TOKEN_ENV}),
    )
    assert choice.env_name == CLAUDE_OAUTH_TOKEN_ENV
    assert choice.fallback_reason is not None
    assert "no caam-published" in choice.fallback_reason


def test_resolve_falls_back_when_slot_absent() -> None:
    choice = resolve_factory_credential_env_name(
        selected_profile="anthropic-4",
        available_env_names=frozenset({CLAUDE_OAUTH_TOKEN_ENV}),
    )
    assert choice.env_name == CLAUDE_OAUTH_TOKEN_ENV
    assert choice.fallback_reason is not None
    assert "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4" in choice.fallback_reason
    assert "anthropic-4" in choice.fallback_reason


def test_read_selected_profile_absent_record_is_none(tmp_path: Path) -> None:
    assert read_selected_profile(home=tmp_path) is None


def test_read_selected_profile_reads_the_record(tmp_path: Path) -> None:
    _write_record(home=tmp_path, payload={"profile": "anthropic-2", "account_uuid": "u"})
    assert read_selected_profile(home=tmp_path) == "anthropic-2"


def test_factory_credential_env_name_ties_read_and_resolve(tmp_path: Path) -> None:
    _write_record(home=tmp_path, payload={"profile": "anthropic-3", "account_uuid": "u"})
    choice = factory_credential_env_name(
        home=tmp_path,
        available_env_names=frozenset({_SLOT}),
    )
    assert choice == FactoryCredentialChoice(env_name=_SLOT, fallback_reason=None)


def test_select_warns_only_on_fallback(tmp_path: Path) -> None:
    # No record → fallback → warn fires once with a non-secret message.
    warnings: list[str] = []
    fallback = select_factory_credential(
        environ={CLAUDE_OAUTH_TOKEN_ENV: "value"},
        home=tmp_path,
        warn=warnings.append,
    )
    assert fallback.env_name == CLAUDE_OAUTH_TOKEN_ENV
    assert len(warnings) == 1
    assert "fallback" in warnings[0]

    # Record + slot present → slot chosen → warn NOT called.
    _write_record(home=tmp_path, payload={"profile": "anthropic-3", "account_uuid": "u"})
    picked: list[str] = []
    chosen = select_factory_credential(
        environ={_SLOT: "value", CLAUDE_OAUTH_TOKEN_ENV: "other"},
        home=tmp_path,
        warn=picked.append,
    )
    assert chosen.env_name == _SLOT
    assert picked == []
