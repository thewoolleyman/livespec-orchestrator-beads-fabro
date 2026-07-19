"""Coverage for the local codex full-access gate.

The gate is pure at SessionStart: env override, committed marker, then OFF.
The explicit refresh command derives the marker from the livespec core fleet
manifest parser plus the fleet contract owner resolver, but tests monkeypatch
those seams in-process and never spawn subprocesses.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_HOOK_PATH = _HOOKS_DIR / "codex_yolo_gate.py"
_MODULE_NAME = "codex_yolo_gate_under_test"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _write_config(*, repo: Path, marker: str) -> None:
    _ = (repo / hook.CONFIG_FILENAME).write_text(
        "{\n"
        '  "template": "livespec",\n'
        '  "url": "https://example.test/not-a-comment", // JSONC comment\n'
        f'  "codex_full_access": {{ "fleet_listed": {marker} }}\n'
        "}\n",
        encoding="utf-8",
    )


def _manifest_source() -> str:
    return (
        "{\n"
        '  "owner": "thewoolleyman",\n'
        '  "fleet": [\n'
        '    {"repo": "livespec", "class": "core"},\n'
        '    {"repo": "livespec-orchestrator-beads-fabro", "class": "impl-plugin"}\n'
        "  ],\n"
        '  "adopters": [\n'
        '    {"repo": "official-adopter", "profile": ["baseline"], "posture": "pinned"}\n'
        "  ]\n"
        "}\n"
    )


def test_gate_state_env_true_wins_over_missing_marker(tmp_path: Path) -> None:
    assert hook.gate_state(env={hook.ENV_OVERRIDE: "true"}, repo=tmp_path) == "on"
    assert hook.gate_state(env={hook.ENV_OVERRIDE: "1"}, repo=tmp_path) == "on"


def test_gate_state_env_false_wins_over_truthy_marker(tmp_path: Path) -> None:
    _write_config(repo=tmp_path, marker="true")

    assert hook.gate_state(env={hook.ENV_OVERRIDE: "false"}, repo=tmp_path) == "off"
    assert hook.gate_state(env={hook.ENV_OVERRIDE: "0"}, repo=tmp_path) == "off"


def test_gate_state_uses_truthy_marker_when_override_is_unset(tmp_path: Path) -> None:
    _write_config(repo=tmp_path, marker="true")

    assert hook.gate_state(env={}, repo=tmp_path) == "on"


def test_gate_state_defaults_off_for_absent_false_or_unknown_marker(tmp_path: Path) -> None:
    assert hook.gate_state(env={}, repo=tmp_path) == "off"
    _write_config(repo=tmp_path, marker="false")
    assert hook.gate_state(env={}, repo=tmp_path) == "off"
    _write_config(repo=tmp_path, marker='"yes"')
    assert hook.gate_state(env={}, repo=tmp_path) == "off"


def test_read_marker_fails_open_for_bad_config_shapes(tmp_path: Path) -> None:
    for source in ("not json", "[]", '{"codex_full_access": []}'):
        _ = (tmp_path / hook.CONFIG_FILENAME).write_text(source, encoding="utf-8")

        assert hook.read_marker(repo=tmp_path) is False


def test_repo_name_from_remote_url_accepts_canonical_github_forms() -> None:
    assert (
        hook.repo_name_from_remote_url(
            remote_url="https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"
        )
        == "livespec-orchestrator-beads-fabro"
    )
    assert (
        hook.repo_name_from_remote_url(
            remote_url="git@github.com:thewoolleyman/official-adopter.git"
        )
        == "official-adopter"
    )


def test_repo_name_from_remote_url_rejects_non_github_urls() -> None:
    assert hook.repo_name_from_remote_url(remote_url="ssh://git.example.test/repo.git") is None


def test_derive_fleet_listed_matches_owner_and_members_or_adopters() -> None:
    assert (
        hook.derive_fleet_listed(
            manifest_source=_manifest_source(),
            owner="thewoolleyman",
            repo="livespec-orchestrator-beads-fabro",
        )
        is True
    )
    assert (
        hook.derive_fleet_listed(
            manifest_source=_manifest_source(),
            owner="thewoolleyman",
            repo="official-adopter",
        )
        is True
    )


def test_derive_fleet_listed_rejects_owner_repo_and_manifest_misses() -> None:
    assert (
        hook.derive_fleet_listed(
            manifest_source=_manifest_source(), owner="someone", repo="livespec"
        )
        is False
    )
    assert (
        hook.derive_fleet_listed(
            manifest_source=_manifest_source(),
            owner="thewoolleyman",
            repo="external",
        )
        is False
    )
    assert (
        hook.derive_fleet_listed(manifest_source="not json", owner="thewoolleyman", repo="livespec")
        is False
    )
    assert (
        hook.derive_fleet_listed(manifest_source=_manifest_source(), owner=None, repo="livespec")
        is False
    )
    assert (
        hook.derive_fleet_listed(
            manifest_source=_manifest_source(), owner="thewoolleyman", repo=None
        )
        is False
    )


def test_derive_fleet_listed_fails_closed_when_parser_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hook, "parse_manifest", None)

    assert (
        hook.derive_fleet_listed(
            manifest_source=_manifest_source(),
            owner="thewoolleyman",
            repo="livespec",
        )
        is False
    )


def test_with_marker_inserts_and_replaces_top_level_block() -> None:
    inserted = hook.with_marker(
        config_text='{\n  "template": "livespec",\n  "implementation": {"plugin": "x"}\n}\n',
        fleet_listed=True,
    )
    assert '"fleet_listed": true' in inserted
    replaced = hook.with_marker(config_text=inserted, fleet_listed=False)
    assert '"fleet_listed": false' in replaced
    assert replaced.count('"codex_full_access"') == 1


def test_with_marker_falls_back_to_final_brace_insertion() -> None:
    updated = hook.with_marker(config_text='{\n  "template": "livespec"\n}\n', fleet_listed=True)

    assert '"codex_full_access"' in updated


def test_with_marker_leaves_unparseable_text_without_a_brace_unchanged() -> None:
    assert hook.with_marker(config_text="not json", fleet_listed=True) == "not json"


def test_main_refresh_writes_manifest_derived_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.jsonc"
    _ = manifest.write_text(_manifest_source(), encoding="utf-8")
    _ = (tmp_path / hook.CONFIG_FILENAME).write_text(
        '{\n  "implementation": {"plugin": "x"}\n}\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    def fake_resolve_owner(*, cwd: Path) -> str:
        assert cwd == tmp_path
        return "thewoolleyman"

    def fake_remote_url_for_repo(*, repo: Path) -> str:
        assert repo == tmp_path
        return "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"

    monkeypatch.setattr(hook, "resolve_owner", fake_resolve_owner)
    monkeypatch.setattr(hook, "remote_url_for_repo", fake_remote_url_for_repo)

    assert hook.main(argv=["refresh", str(manifest)]) == 0

    assert hook.read_marker(repo=tmp_path) is True


def test_main_refresh_fails_open_when_inputs_are_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert hook.main(argv=["refresh", str(tmp_path / "missing.jsonc")]) == 0


def test_main_rejects_unknown_cli_shape() -> None:
    assert hook.main(argv=[]) == 2


def test_main_refresh_derives_off_without_owner_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.jsonc"
    _ = manifest.write_text(_manifest_source(), encoding="utf-8")
    _ = (tmp_path / hook.CONFIG_FILENAME).write_text(
        '{\n  "implementation": {"plugin": "x"}\n}\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    def fake_remote_url_for_repo(*, repo: Path) -> str:
        assert repo == tmp_path
        return "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"

    monkeypatch.setattr(hook, "resolve_owner", None)
    monkeypatch.setattr(hook, "remote_url_for_repo", fake_remote_url_for_repo)

    assert hook.main(argv=["refresh", str(manifest)]) == 0

    assert hook.read_marker(repo=tmp_path) is False


def test_committed_repo_marker_keeps_this_repo_gate_on() -> None:
    assert hook.gate_state(env={}, repo=_REPO_ROOT) == "on"


def test_with_marker_handles_implementation_line_without_trailing_newline() -> None:
    updated = hook.with_marker(config_text='{\n  "implementation": {}', fleet_listed=True)

    assert '"codex_full_access"' in updated


def test_read_marker_handles_escaped_string_and_eof_comment(tmp_path: Path) -> None:
    _ = (tmp_path / hook.CONFIG_FILENAME).write_text(
        "{\n"
        '  "quoted": "contains \\"// not a comment\\" and \\\\ slash",\n'
        '  "codex_full_access": { "fleet_listed": true }\n'
        "} // eof comment",
        encoding="utf-8",
    )

    assert hook.read_marker(repo=tmp_path) is True


def test_remote_url_for_repo_returns_stdout_from_successful_runner(tmp_path: Path) -> None:
    class Completed:
        returncode = 0
        stdout = "https://github.com/thewoolleyman/example.git\n"

    def fake_run(*args, **kwargs):
        assert args == (["git", "remote", "get-url", "origin"],)
        assert kwargs["cwd"] == str(tmp_path)
        return Completed()

    assert (
        hook.remote_url_for_repo(repo=tmp_path, run=fake_run)
        == "https://github.com/thewoolleyman/example.git"
    )


def test_remote_url_for_repo_returns_empty_string_from_failed_runner(tmp_path: Path) -> None:
    class Completed:
        returncode = 1
        stdout = "ignored\n"

    def fake_run(*args: object, **kwargs: object) -> Completed:
        assert args == (["git", "remote", "get-url", "origin"],)
        assert kwargs["cwd"] == str(tmp_path)
        return Completed()

    assert hook.remote_url_for_repo(repo=tmp_path, run=fake_run) == ""
