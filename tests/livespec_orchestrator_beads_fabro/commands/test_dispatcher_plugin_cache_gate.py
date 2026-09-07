"""Behavioural tests for the in-sandbox plugin-cache gate (bd-ib-dbqb, bd-ib-bb41.9).

These EXECUTE the rendered prepare step against a temporary Claude plugins root
rather than asserting the text it renders. That distinction is the whole point:
the failure this gate exists to catch — a registry naming a build whose cache
directory is absent or half-copied — was itself a case of a verification that
passed on a cache it had not actually inspected, so a test that only reads the
rendered script would repeat the original defect one level up.

The gate runs as a `[[run.prepare.steps]]` entry, which fabro executes BEFORE
any ACP session. "Repaired before the agent runs" is therefore a property of
where the step sits, and `test_overlay_appends_the_gate_as_a_prepare_step`
pins that placement.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT.joinpath(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    "/_dispatcher_plugin_cache_gate.py"
)
_MANIFEST = {"required_paths": ["plugin.json", "scripts/bin"]}


def _write_json(*, path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _complete_cache(*, cache_dir: Path) -> Path:
    (cache_dir / "scripts" / "bin").mkdir(parents=True, exist_ok=True)
    (cache_dir / "plugin.json").write_text("{}", encoding="utf-8")
    _write_json(path=cache_dir / "cache-manifest.json", payload=_MANIFEST)
    return cache_dir


def _incomplete_cache(*, cache_dir: Path) -> Path:
    """A cache copy that landed WITHOUT `scripts/bin` — the bd-ib-dbqb shape."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "plugin.json").write_text("{}", encoding="utf-8")
    _write_json(path=cache_dir / "cache-manifest.json", payload=_MANIFEST)
    return cache_dir


def _run_gate(*, plugins_root: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    module = importlib.import_module(_MODULE_NAME)
    script = tmp_path / "gate.sh"
    script.write_text(module.plugin_cache_gate_script(), encoding="utf-8")
    return subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(tmp_path / "unused-home"),
            module.SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root),
        },
    )


def test_the_gate_module_is_present() -> None:
    """The gate must be a committed module, not prose about one."""
    assert _MODULE_PATH.is_file()


def test_a_registered_but_empty_cache_is_repaired(tmp_path: Path) -> None:
    """The measured bb41.9 shape: a registry entry whose cache root never landed."""
    plugins_root = tmp_path / "plugins"
    missing = plugins_root / "cache" / "mkt" / "plug" / "59348141199a"
    _write_json(
        path=plugins_root / "installed_plugins.json",
        payload={
            "version": 2,
            "plugins": {"plug@mkt": [{"installPath": str(missing), "version": "59348141199a"}]},
        },
    )

    result = _run_gate(plugins_root=plugins_root, tmp_path=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "does not exist" in result.stderr
    registry = json.loads((plugins_root / "installed_plugins.json").read_text(encoding="utf-8"))
    assert registry["plugins"]["plug@mkt"] == []


def test_an_incomplete_cache_is_removed_and_a_complete_one_survives(tmp_path: Path) -> None:
    """`required_paths` is what separates the two; both are otherwise plausible."""
    plugins_root = tmp_path / "plugins"
    cache = plugins_root / "cache" / "mkt" / "plug"
    broken = _incomplete_cache(cache_dir=cache / "becb27fc76c4")
    sound = _complete_cache(cache_dir=cache / "9a8dc206f0dd")
    _write_json(
        path=plugins_root / "installed_plugins.json",
        payload={
            "version": 2,
            "plugins": {
                "plug@mkt": [
                    {"installPath": str(broken), "version": "becb27fc76c4"},
                    {"installPath": str(sound), "version": "9a8dc206f0dd"},
                ]
            },
        },
    )

    result = _run_gate(plugins_root=plugins_root, tmp_path=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "missing required path scripts/bin" in result.stderr
    assert not broken.exists()
    assert sound.is_dir()
    registry = json.loads((plugins_root / "installed_plugins.json").read_text(encoding="utf-8"))
    assert [record["version"] for record in registry["plugins"]["plug@mkt"]] == ["9a8dc206f0dd"]


def test_a_cache_truncated_before_its_manifest_is_still_repaired(tmp_path: Path) -> None:
    """A copy missing `cache-manifest.json` declares no required paths at all.

    Without the separate `plugin.json` check such a copy reads as complete, so
    the emptiest half-copy would be the one that slips through.
    """
    plugins_root = tmp_path / "plugins"
    stump = plugins_root / "cache" / "mkt" / "plug" / "deadbeef"
    stump.mkdir(parents=True)
    _write_json(
        path=plugins_root / "installed_plugins.json",
        payload={"version": 2, "plugins": {"plug@mkt": [{"installPath": str(stump)}]}},
    )

    result = _run_gate(plugins_root=plugins_root, tmp_path=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "has no plugin.json" in result.stderr
    assert not stump.exists()


def test_the_gate_refuses_to_delete_outside_the_cache_root(tmp_path: Path) -> None:
    """An unrepairable record fails the run in setup instead of at the PR node."""
    plugins_root = tmp_path / "plugins"
    outside = tmp_path / "not-the-cache"
    outside.mkdir()
    _write_json(
        path=plugins_root / "installed_plugins.json",
        payload={"version": 2, "plugins": {"plug@mkt": [{"installPath": str(outside)}]}},
    )

    result = _run_gate(plugins_root=plugins_root, tmp_path=tmp_path)

    assert result.returncode == 1
    assert "REFUSED to remove a cache outside" in result.stderr
    assert outside.is_dir()


def test_the_run_is_pinned_to_the_build_resolved_at_prepare_time(tmp_path: Path) -> None:
    """One run, one build: the floating marketplace ref is rewritten to a commit."""
    module = importlib.import_module(_MODULE_NAME)
    plugins_root = tmp_path / "plugins"
    clone = plugins_root / "marketplaces" / "mkt"
    clone.mkdir(parents=True)
    for argv in (
        ["git", "init", "--quiet", str(clone)],
        [
            "git",
            "-C",
            str(clone),
            "-c",
            "user.email=t@e",
            "-c",
            "user.name=t",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "seed",
        ],
    ):
        subprocess.run(argv, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _write_json(
        path=plugins_root / "known_marketplaces.json",
        payload={
            "mkt": {
                "source": {"source": "github", "repo": "o/r", "ref": "release"},
                "installLocation": str(clone),
            }
        },
    )
    sound = _complete_cache(cache_dir=plugins_root / "cache" / "mkt" / "plug" / "9a8dc206f0dd")
    _write_json(
        path=plugins_root / "installed_plugins.json",
        payload={
            "version": 2,
            "plugins": {"plug@mkt": [{"installPath": str(sound), "version": "9a8dc206f0dd"}]},
        },
    )

    result = _run_gate(plugins_root=plugins_root, tmp_path=tmp_path)

    assert result.returncode == 0, result.stderr
    marketplaces = json.loads(
        (plugins_root / "known_marketplaces.json").read_text(encoding="utf-8")
    )
    assert marketplaces["mkt"]["source"]["ref"] == head
    pin = json.loads((plugins_root / module.PLUGIN_BUILD_PIN_FILENAME).read_text(encoding="utf-8"))
    assert pin["marketplaces"]["mkt"] == {"previous_ref": "release", "ref": head}
    assert pin["builds"]["plug@mkt"] == ["9a8dc206f0dd"]


def test_an_unprovisioned_sandbox_is_not_an_error(tmp_path: Path) -> None:
    """A sandbox with nothing registered yet reports that and lets the run go on."""
    plugins_root = tmp_path / "plugins"

    result = _run_gate(plugins_root=plugins_root, tmp_path=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "no installed-plugin records" in result.stderr


def test_overlay_appends_the_gate_as_a_prepare_step() -> None:
    """Placement is the guarantee: prepare steps run before any ACP session."""
    module = importlib.import_module(_MODULE_NAME)
    block = module.plugin_cache_gate_prepare_steps_block()

    assert block.startswith("\n# --- Dispatcher-materialized Claude plugin-cache")
    assert "[[run.prepare.steps]]" in block
    assert "cache-manifest.json" in block
    assert "required_paths" in block
    assert module.plugin_cache_gate_script() in block
