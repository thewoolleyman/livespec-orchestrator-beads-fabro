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

RE-ENTRY AT THE PR STAGE BOUNDARY (bd-ib-cewr.3). Prepare runs once, and the
registry it verified is mutated afterwards: every later ACP session runs its own
plugin update. Measured 2026-09-08 across three console runs, the sandbox
registry carried NO orchestrator record at janitor time (the TUI e2e suite was
12/12 green) and named build `1efcb86825de` by the pr stage, whose cache had no
`scripts/bin` — so the pre-push hook failed on a plugin root the run never
resolved. The gate is therefore re-entrant: the prepare pass RECORDS the run's
build resolution and materializes the gate program, and the pr stage re-runs
that program before it pushes, reverting any build the run did not start with
and refusing by name on an unmaterialized cache it cannot repair.
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
_PR_PROMPT_PATH = _REPO_ROOT.joinpath(
    ".claude-plugin/.fabro/workflows/implement-work-item/prompts/pr.md"
)
_MANIFEST = {"required_paths": ["plugin.json", "scripts/bin"]}
# The plugin key and build id the three console runs failed on, kept verbatim so
# the regression test reproduces the measured signature rather than a paraphrase.
_ORCHESTRATOR_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
_UNMATERIALIZED_BUILD = "1efcb86825de"


def module_marker(*, name: str) -> str:
    """The gate's named-marker constant, read from the module under test.

    Read rather than spelled: the marker the sandbox emits and the marker a
    test looks for must be ONE string, or the test passes on a signature the
    run never prints.
    """
    module = importlib.import_module(_MODULE_NAME)
    return str(getattr(module, name))


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


def _gate_env(*, plugins_root: Path, tmp_path: Path) -> dict[str, str]:
    module = importlib.import_module(_MODULE_NAME)
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path / "unused-home"),
        module.SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root),
    }


def _run_gate(*, plugins_root: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    module = importlib.import_module(_MODULE_NAME)
    script = tmp_path / "gate.sh"
    script.write_text(module.plugin_cache_gate_script(), encoding="utf-8")
    return subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=_gate_env(plugins_root=plugins_root, tmp_path=tmp_path),
    )


def _run_pin_gate(*, plugins_root: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Re-enter the gate the way the pr stage does — through its published command."""
    module = importlib.import_module(_MODULE_NAME)
    return subprocess.run(
        ["bash", "-c", module.plugin_pin_gate_command()],
        capture_output=True,
        text=True,
        check=False,
        env=_gate_env(plugins_root=plugins_root, tmp_path=tmp_path),
    )


def _register(*, plugins_root: Path, plugin: str, cache_dir: Path, build: str) -> None:
    """Append one installed-plugin record, the way a session's update would."""
    registry_path = plugins_root / "installed_plugins.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    records = registry["plugins"].setdefault(plugin, [])
    records.append({"installPath": str(cache_dir), "version": build})
    _write_json(path=registry_path, payload=registry)


def _registered_builds(*, plugins_root: Path, plugin: str) -> list[str]:
    registry_path = plugins_root / "installed_plugins.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    return [str(record["version"]) for record in registry["plugins"][plugin]]


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


def test_the_prepare_pass_materializes_the_gate_program_for_later_stages(
    tmp_path: Path,
) -> None:
    """A one-shot heredoc cannot be re-entered; the program has to land on disk."""
    module = importlib.import_module(_MODULE_NAME)
    plugins_root = tmp_path / "plugins"

    result = _run_gate(plugins_root=plugins_root, tmp_path=tmp_path)

    assert result.returncode == 0, result.stderr
    program = plugins_root / module.PLUGIN_GATE_PROGRAM_FILENAME
    assert program.is_file()
    assert "cache-manifest.json" in program.read_text(encoding="utf-8")


def test_a_later_stage_keeps_the_build_the_run_resolved_at_start(tmp_path: Path) -> None:
    """Criterion 1: a release registered mid-run does not move the run's build.

    The newer cache here is COMPLETE on purpose. Cache repair cannot explain the
    outcome, so the assertion isolates the per-run pin: only the pin knows the
    build is one this run never resolved.
    """
    plugins_root = tmp_path / "plugins"
    cache = plugins_root / "cache" / "mkt" / "plug"
    started_with = _complete_cache(cache_dir=cache / "39cf53dee07c")
    _write_json(
        path=plugins_root / "installed_plugins.json",
        payload={
            "version": 2,
            "plugins": {
                "plug@mkt": [{"installPath": str(started_with), "version": "39cf53dee07c"}]
            },
        },
    )
    prepare = _run_gate(plugins_root=plugins_root, tmp_path=tmp_path)
    assert prepare.returncode == 0, prepare.stderr

    newer = _complete_cache(cache_dir=cache / _UNMATERIALIZED_BUILD)
    _register(
        plugins_root=plugins_root,
        plugin="plug@mkt",
        cache_dir=newer,
        build=_UNMATERIALIZED_BUILD,
    )

    boundary = _run_pin_gate(plugins_root=plugins_root, tmp_path=tmp_path)

    assert boundary.returncode == 0, boundary.stderr
    assert module_marker(name="PLUGIN_BUILD_ADVANCED_MARKER") in boundary.stderr
    assert _registered_builds(plugins_root=plugins_root, plugin="plug@mkt") == ["39cf53dee07c"]


def test_an_unmaterialized_build_outside_the_cache_refuses_by_name(tmp_path: Path) -> None:
    """Criterion 2: an unrepairable entry refuses, naming the condition."""
    plugins_root = tmp_path / "plugins"
    outside = _incomplete_cache(cache_dir=tmp_path / "not-the-cache" / _UNMATERIALIZED_BUILD)
    _write_json(
        path=plugins_root / "installed_plugins.json",
        payload={
            "version": 2,
            "plugins": {
                _ORCHESTRATOR_KEY: [{"installPath": str(outside), "version": _UNMATERIALIZED_BUILD}]
            },
        },
    )

    result = _run_gate(plugins_root=plugins_root, tmp_path=tmp_path)

    assert result.returncode == 1
    assert module_marker(name="PLUGIN_CACHE_UNMATERIALIZED_MARKER") in result.stderr
    assert "missing required path scripts/bin" in result.stderr


def test_the_console_missing_scripts_bin_signature_is_cleared_before_the_push(
    tmp_path: Path,
) -> None:
    """Criterion 3: the measured console signature, reproduced end to end.

    Prepare sees a sandbox with no orchestrator record — the state the three
    console runs' janitor observed, with the TUI suite 12/12 green. A later ACP
    session's plugin update then registers `1efcb86825de` with a cache carrying
    no `scripts/bin`, which is the root the TUI refused. Re-entering the gate at
    the pr stage boundary leaves nothing for that resolution to reach.
    """
    plugins_root = tmp_path / "plugins"
    _write_json(
        path=plugins_root / "installed_plugins.json",
        payload={"version": 2, "plugins": {}},
    )
    prepare = _run_gate(plugins_root=plugins_root, tmp_path=tmp_path)
    assert prepare.returncode == 0, prepare.stderr

    unmaterialized = _incomplete_cache(
        cache_dir=plugins_root
        / "cache"
        / "livespec-orchestrator-beads-fabro"
        / "livespec-orchestrator-beads-fabro"
        / _UNMATERIALIZED_BUILD
    )
    _register(
        plugins_root=plugins_root,
        plugin=_ORCHESTRATOR_KEY,
        cache_dir=unmaterialized,
        build=_UNMATERIALIZED_BUILD,
    )

    boundary = _run_pin_gate(plugins_root=plugins_root, tmp_path=tmp_path)

    assert boundary.returncode == 0, boundary.stderr
    assert module_marker(name="PLUGIN_CACHE_UNMATERIALIZED_MARKER") in boundary.stderr
    assert "missing required path scripts/bin" in boundary.stderr
    assert not unmaterialized.exists()
    assert _registered_builds(plugins_root=plugins_root, plugin=_ORCHESTRATOR_KEY) == []


def test_the_pr_stage_prompt_re_enters_the_gate_before_it_pushes() -> None:
    """The stage boundary is only a guarantee if the pr recipe actually runs it."""
    module = importlib.import_module(_MODULE_NAME)
    prompt = _PR_PROMPT_PATH.read_text(encoding="utf-8")

    command_index = prompt.index(module.plugin_pin_gate_command())
    push_index = prompt.index("git push -u origin HEAD:refs/heads/feat/<work-item-id>")
    assert command_index < push_index
    assert module.PLUGIN_CACHE_UNMATERIALIZED_MARKER in prompt
