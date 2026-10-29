"""Tests for the beads-private `acp_preflight_config` check.

The check moves the Dispatcher's own ACP preflight evaluation from dispatch
admission to commit time: a chain that names a model the catalog does not
declare is refused here, before it can be copied to a fleet repository and
refuse every dispatch there. Every case drives `main()` through the real
`resolve_acp_preflight`, so the verdict under test is the Dispatcher's rather
than a second reading of the configuration.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "acp_preflight_config.py"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acp_preflight_config_under_test", _CHECK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_CHECK = _load_check()

_CODEX_NODE: dict[str, Any] = {"agent": "codex-acp", "model": "gpt-6-sol", "effort": "high"}
_CLAUDE_FALLBACK: dict[str, Any] = {
    "agent": "claude-acp",
    "model": "claude-sonnet-5-5",
    "effort": "medium",
}
_CLAUDE_CATALOG_ENTRY: dict[str, Any] = {
    "display_name": "Claude Sonnet 5.5",
    "pricing": {
        "model": "claude-sonnet-5-5",
        "input_usd_per_million": 2.0,
        "output_usd_per_million": 10.0,
        "cache_write_usd_per_million": 2.5,
        "cache_read_usd_per_million": 0.2,
    },
}
_CODEX_CATALOG_ENTRY: dict[str, Any] = {
    "display_name": "GPT-6 Sol",
    "pricing": {
        "model": "gpt-6-sol",
        "input_usd_per_million": 2.0,
        "output_usd_per_million": 10.0,
        "cache_write_usd_per_million": 2.5,
        "cache_read_usd_per_million": 0.2,
    },
}


def _write_config(*, repo: Path, catalog: dict[str, Any]) -> Path:
    dispatcher: dict[str, Any] = {
        "acp_nodes": {"disposition": {**_CODEX_NODE, "fallbacks": [_CLAUDE_FALLBACK]}}
    }
    if catalog:
        dispatcher["model_catalog"] = catalog
    path = repo / ".livespec.jsonc"
    _ = path.write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    return repo


def test_unresolvable_fallback_model_fails_naming_the_field_and_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _write_config(repo=tmp_path, catalog={})
    monkeypatch.setattr(sys, "argv", ["acp_preflight_config", str(repo)])
    exit_code = _CHECK.main()
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "fallbacks[0].model" in err
    assert "claude-sonnet-5-5" in err


def test_declared_fallback_model_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _write_config(
        repo=tmp_path,
        catalog={
            "anthropic/claude-sonnet-5-5": _CLAUDE_CATALOG_ENTRY,
            "openai/gpt-6-sol": _CODEX_CATALOG_ENTRY,
        },
    )
    monkeypatch.setattr(sys, "argv", ["acp_preflight_config", str(repo)])
    assert _CHECK.main() == 0


@pytest.mark.committed_routing_lint
def test_committed_configuration_passes_with_no_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket.socket, "connect", None)
    monkeypatch.setattr(sys, "argv", ["acp_preflight_config"])
    assert _CHECK.main() == 0


@pytest.mark.committed_routing_lint
def test_evaluation_supplies_no_probe_headroom_factory_reader_or_journal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = _CHECK.resolve_acp_preflight
    calls: list[dict[str, object]] = []

    def _spy(**kwargs: Any) -> object:
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(_CHECK, "resolve_acp_preflight", _spy)
    monkeypatch.setattr(sys, "argv", ["acp_preflight_config"])
    assert _CHECK.main() == 0
    assert len(calls) == 1
    assert calls[0]["repo"] == _REPO_ROOT
    assert calls[0]["journal_path"] is None
    assert set(calls[0]) == {"repo", "journal_path", "now_iso"}
