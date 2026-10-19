"""Tests for dispatcher factory ledger pinning."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _config as config_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger import (
    args_with_dispatch_factory_target,
    args_with_earlier_dispatch_factory_target,
    resolve_dispatch_factory_target,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    dispatch_factory_for,
    record_dispatch_factory,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id="li-factory",
        type="task",
        status="ready",
        title="Factory target",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_env_factory_is_recorded_when_no_cli_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())
    monkeypatch.setenv("LIVESPEC_FABRO_FACTORY", "env-remote")

    target = resolve_dispatch_factory_target(
        args=argparse.Namespace(factory=None),
        repo=repo,
        work_item_id="li-factory",
    )

    assert target.name == "env-remote"
    assert dispatch_factory_for(path=_config(), work_item_id="li-factory") == "env-remote"


def test_args_clone_records_cli_factory_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {"prefix": "bd-ib"},
            "dispatcher": {
              "factories": {
                "cli": {"server": "https://cli.example.test"}
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())
    monkeypatch.setenv("LIVESPEC_FABRO_FACTORY", "env-remote")
    args = argparse.Namespace(factory="cli", keep="value")

    cloned = args_with_dispatch_factory_target(
        args=args,
        repo=repo,
        work_item_id="li-factory",
    )

    assert cloned is not args
    assert cloned.keep == "value"
    assert cloned.fabro_factory_target.name == "cli"
    assert cloned.fabro_factory_target.server == "https://cli.example.test"
    assert dispatch_factory_for(path=_config(), work_item_id="li-factory") == "cli"


def test_missing_factories_block_has_no_configured_factory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )

    assert hasattr(config_module, "has_fabro_factory")
    assert config_module.has_fabro_factory(cwd=repo, factory="default") is False


def test_recorded_factory_is_reused_when_names_are_unconstrained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())
    record_dispatch_factory(path=_config(), work_item_id="li-factory", factory="remote")
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)

    target = resolve_dispatch_factory_target(
        args=argparse.Namespace(factory=None),
        repo=repo,
        work_item_id="li-factory",
    )

    assert target.name == "remote"
    assert target.server is None
    assert dispatch_factory_for(path=_config(), work_item_id="li-factory") == "remote"


def test_unrecorded_factory_uses_current_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {"prefix": "bd-ib"},
            "dispatcher": {
              "default_factory": "hp",
              "factories": {
                "hp": {"server": "https://hp.example.test"}
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)

    target = resolve_dispatch_factory_target(
        args=argparse.Namespace(factory=None),
        repo=repo,
        work_item_id="li-factory",
    )

    assert target.name == "hp"
    assert target.server == "https://hp.example.test"
    assert dispatch_factory_for(path=_config(), work_item_id="li-factory") == "hp"


def test_legacy_earlier_dispatch_factory_ignores_an_invocation_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing historical pin reads the configured default, not caller intent."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {"prefix": "bd-ib"},
            "dispatcher": {
              "default_factory": "hp",
              "factories": {
                "hp": {"server": "https://hp.example.test"},
                "caller": {"server": "https://caller.example.test"}
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())
    monkeypatch.setenv("LIVESPEC_FABRO_FACTORY", "caller")

    earlier = args_with_earlier_dispatch_factory_target(
        args=argparse.Namespace(fabro_bin=None),
        repo=repo,
        work_item_id="li-factory",
    )

    assert earlier.fabro_factory_target.name == "hp"
    assert earlier.fabro_factory_target.server == "https://hp.example.test"


def test_configured_recorded_factory_is_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {"prefix": "bd-ib"},
            "dispatcher": {
              "default_factory": "hp",
              "factories": {
                "hp": {"server": "https://hp.example.test"},
                "vps": {"server": "http://127.0.0.1:32276"}
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())
    record_dispatch_factory(path=_config(), work_item_id="li-factory", factory="vps")
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)

    target = resolve_dispatch_factory_target(
        args=argparse.Namespace(factory=None),
        repo=repo,
        work_item_id="li-factory",
    )

    assert target.name == "vps"
    assert target.server == "http://127.0.0.1:32276"
    assert dispatch_factory_for(path=_config(), work_item_id="li-factory") == "vps"


def test_stale_recorded_factory_falls_back_to_current_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A renamed-away retry marker must not fall through to ambient Fabro."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {"prefix": "bd-ib"},
            "dispatcher": {
              "default_factory": "hp",
              "factories": {
                "hp": {"server": "https://hp.example.test"},
                "vps": {"server": "http://127.0.0.1:32276"}
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())
    record_dispatch_factory(path=_config(), work_item_id="li-factory", factory="default")
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)

    target = resolve_dispatch_factory_target(
        args=argparse.Namespace(factory=None),
        repo=repo,
        work_item_id="li-factory",
    )

    assert target.name == "hp"
    assert target.server == "https://hp.example.test"
    assert dispatch_factory_for(path=_config(), work_item_id="li-factory") == "hp"
