"""Coverage for the codex-YOLO SessionStart re-apply hook.

The hook forces every cached openai-codex `lib/codex.mjs` sandbox chokepoint to
`danger-full-access` and emits a loud stderr WARNING when the chokepoint has
drifted upstream (the canary — see `plan/codex-yolo-sandbox/`).

`.claude/hooks/` is not an importable package, so the module is loaded by file
location — the same idiom `test_fleet_pat_dispatch_surface_helpers.py` uses.
Every test here is PURE: no subprocess spawns the `.sh` wrapper
(`check-tests-no-subprocess-spawn`); `main()` is driven in-process with `HOME`
pointed at a `tmp_path` fake plugin cache.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_PATH = _REPO_ROOT / ".claude" / "hooks" / "codex_yolo_reapply.py"
_MODULE_NAME = "codex_yolo_reapply_under_test"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _cached_mjs(*, home: Path, version: str) -> Path:
    """Create (and return) the cached `codex.mjs` path for a plugin version."""
    path = home / ".claude/plugins/cache/openai-codex/codex" / version / "scripts/lib/codex.mjs"
    path.parent.mkdir(parents=True)
    return path


def _stock_source() -> str:
    return (
        "export function buildThreadParams(options) {\n"
        f"  return {{ {hook.STOCK}, approvalPolicy: 'never' }};\n"
        "}\n"
        "export function buildResumeParams(options) {\n"
        f"  return {{ {hook.STOCK} }};\n"
        "}\n"
    )


def test_classify_state_absent_when_content_is_none() -> None:
    assert hook.classify_state(content=None) == "absent"


def test_classify_state_stock_when_upstream_read_only_default_present() -> None:
    assert hook.classify_state(content=_stock_source()) == "stock"


def test_classify_state_patched_when_our_sentinel_present() -> None:
    patched = _stock_source().replace(hook.STOCK, hook.PATCHED)

    assert hook.classify_state(content=patched) == "patched"


def test_classify_state_drift_when_neither_marker_present() -> None:
    restructured = "export function buildThreadParams(o) { return resolveSandbox(o); }\n"

    assert hook.classify_state(content=restructured) == "drift"


def test_apply_patch_rewrites_every_stock_chokepoint() -> None:
    patched = hook.apply_patch(content=_stock_source())

    assert hook.STOCK not in patched
    assert patched.count(hook.PATCHED) == 2


def test_apply_patch_is_a_noop_when_no_stock_chokepoint_present() -> None:
    already = _stock_source().replace(hook.STOCK, hook.PATCHED)

    assert hook.apply_patch(content=already) == already


def test_read_text_or_none_returns_file_contents(tmp_path: Path) -> None:
    target = tmp_path / "codex.mjs"
    _ = target.write_text("contents", encoding="utf-8")

    assert hook.read_text_or_none(path=target) == "contents"


def test_read_text_or_none_returns_none_for_an_unreadable_path(tmp_path: Path) -> None:
    # A directory raises IsADirectoryError (an OSError) on read_text — the
    # fail-open seam that keeps a session start from ever erroring out.
    assert hook.read_text_or_none(path=tmp_path) is None


def test_cached_codex_mjs_paths_finds_every_cached_version_sorted(tmp_path: Path) -> None:
    newer = _cached_mjs(home=tmp_path, version="1.0.7")
    older = _cached_mjs(home=tmp_path, version="1.0.6")
    for path in (newer, older):
        _ = path.write_text(_stock_source(), encoding="utf-8")

    assert hook.cached_codex_mjs_paths(home=tmp_path) == [older, newer]


def test_cached_codex_mjs_paths_is_empty_without_a_plugin_cache(tmp_path: Path) -> None:
    assert hook.cached_codex_mjs_paths(home=tmp_path) == []


def test_main_patches_a_stock_chokepoint_and_reports_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    target = _cached_mjs(home=tmp_path, version="1.0.6")
    _ = target.write_text(_stock_source(), encoding="utf-8")

    assert hook.main() == 0

    rewritten = target.read_text(encoding="utf-8")
    assert hook.STOCK not in rewritten
    assert rewritten.count(hook.PATCHED) == 2
    captured = capsys.readouterr()
    assert str(target) in captured.out
    assert captured.err == ""


def test_main_is_idempotent_on_an_already_patched_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    target = _cached_mjs(home=tmp_path, version="1.0.6")
    already = _stock_source().replace(hook.STOCK, hook.PATCHED)
    _ = target.write_text(already, encoding="utf-8")

    assert hook.main() == 0

    assert target.read_text(encoding="utf-8") == already
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_main_warns_loudly_and_changes_nothing_when_the_chokepoint_drifted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    target = _cached_mjs(home=tmp_path, version="1.0.6")
    restructured = "export function buildThreadParams(o) { return resolveSandbox(o); }\n"
    _ = target.write_text(restructured, encoding="utf-8")

    assert hook.main() == 0

    assert target.read_text(encoding="utf-8") == restructured
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "WARNING" in captured.err
    assert str(target) in captured.err


def test_main_is_a_silent_noop_without_a_plugin_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert hook.main() == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_main_skips_a_glob_match_that_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    # A directory named codex.mjs still matches the glob; reading it fails.
    unreadable = _cached_mjs(home=tmp_path, version="1.0.6")
    unreadable.mkdir()

    assert hook.main() == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
