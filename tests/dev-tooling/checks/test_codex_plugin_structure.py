"""Tests for the `codex_plugin_structure` structural check.

The check validates the orchestrator plugin's Codex cross-runtime surface:
the repo-root `.agents/plugins/marketplace.json` catalog, the nested
`.claude-plugin/.codex-plugin/plugin.json` manifest, the SIX thin
wrapper-backed `.codex-plugin/skills/<op>/SKILL.md` bindings (next,
list-work-items, list-plan-threads, detect-impl-gaps, needs-attention, drive), and the FIVE prose-backed
heavyweight bindings (capture-work-item, capture-impl-gaps,
capture-spec-drift, implement, groom) that read `prose/<op>.md` instead of
self-invoking a wrapper. The P3b prose extraction is complete — implement
and groom flipped from pending to prose-backed at P3b PR-3 — so no
heavyweight op remains pending and `_PENDING_CODEX_OPS` is empty (retained
so a future pending op's skill dir would still be asserted ABSENT).

The check is pure-filesystem (no beads / no store), so these tests build a
COMPLETE fixture surface under `tmp_path`, monkeypatch the check module's
path constants onto that tree, and drive `main()` plus the helpers
directly. `monkeypatch.chdir` is applied for parity with the other
dev-tooling check tests.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "codex_plugin_structure.py"
_CHECK_MODULE_NAME = "codex_plugin_structure_under_test"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_CHECK_MODULE_NAME, _CHECK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_CHECK_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_CHECK = _load_check()

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_DESCRIPTION = "Beads/Dolt-backed implementation plugin for livespec."
_VERSION = "0.1.0"

_PRESENT_OPS = {
    "next": "next.py",
    "list-work-items": "list_work_items.py",
    "list-plan-threads": "list_plan_threads.py",
    "detect-impl-gaps": "detect_impl_gaps.py",
    "needs-attention": "needs_attention.py",
    "drive": "drive.py",
}
_PRESENT_PROSE_OPS = (
    "capture-work-item",
    "capture-impl-gaps",
    "capture-spec-drift",
    "implement",
    "groom",
    "plan",
)
# The P3b prose extraction is complete: no heavyweight op remains pending.
_PENDING_OPS: tuple[str, ...] = ()

_RESOLUTION_BLOCK = (
    "## Resolving the plugin root\n\n"
    "```bash\n"
    'PLUGIN_ROOT="$LIVESPEC_ORCH_PLUGIN_ROOT"\n'
    'if [ -z "$PLUGIN_ROOT" ] && [ -d "./.claude-plugin/scripts/bin" ]; then\n'
    '  CANDIDATE_PLUGIN_ROOT="$(pwd)/.claude-plugin"\n'
    '  if [ -f "$CANDIDATE_PLUGIN_ROOT/plugin.json" ] && '
    "python3 - \"$CANDIDATE_PLUGIN_ROOT/plugin.json\" <<'PY'\n"
    "import json\n"
    "import sys\n"
    "\n"
    "try:\n"
    '    with open(sys.argv[1], encoding="utf-8") as f:\n'
    "        data = json.load(f)\n"
    "except Exception:\n"
    "    sys.exit(1)\n"
    f'sys.exit(0 if data.get("name") == "{_PLUGIN_NAME}" else 1)\n'
    "PY\n"
    "  then\n"
    '    PLUGIN_ROOT="$CANDIDATE_PLUGIN_ROOT"\n'
    "  fi\n"
    "fi\n"
    f"codex plugin list --json -m {_PLUGIN_NAME}\n"
    "```\n"
)


def _present_body(*, op: str, script: str) -> str:
    return (
        f"---\nname: {op}\ndescription: Thin Codex binding for {op}.\n---\n\n"
        f"# {op} — Codex binding\n\n{_RESOLUTION_BLOCK}\n"
        "## Invocation\n\n"
        f'```bash\npython3 "$PLUGIN_ROOT/scripts/bin/{script}" "$@"\n```\n'
    )


def _present_prose_body(*, op: str) -> str:
    """A valid prose-backed Codex binding body: reads `prose/<op>.md`, no wrapper."""
    return (
        f"---\nname: {op}\ndescription: Thin Codex binding for {op}.\n---\n\n"
        f"# {op} — Codex binding\n\n{_RESOLUTION_BLOCK}\n"
        "## Invocation\n\n"
        f'```bash\ncat "$PLUGIN_ROOT/prose/{op}.md"\n```\n'
    )


def _write_surface(*, root: Path) -> None:
    """Write a fully-valid present-op Codex surface under `root` (a fake repo root).

    Present = the six wrapper-backed thin ops plus the three prose-backed
    heavyweight capture ops.
    """
    claude_dir = root / ".claude-plugin"
    codex_dir = claude_dir / ".codex-plugin"
    skills_dir = codex_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    _ = (claude_dir / "plugin.json").write_text(
        json.dumps({"name": _PLUGIN_NAME, "version": _VERSION, "description": _DESCRIPTION}),
        encoding="utf-8",
    )

    market_dir = root / ".agents" / "plugins"
    market_dir.mkdir(parents=True, exist_ok=True)
    _ = (market_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": _PLUGIN_NAME,
                "plugins": [
                    {
                        "name": _PLUGIN_NAME,
                        "source": {"source": "local", "path": "./.claude-plugin"},
                        "description": _DESCRIPTION,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    _ = (codex_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": _PLUGIN_NAME,
                "version": _VERSION,
                "description": _DESCRIPTION,
                "skills": "./.codex-plugin/skills/",
            }
        ),
        encoding="utf-8",
    )

    for op, script in _PRESENT_OPS.items():
        (skills_dir / op).mkdir(parents=True, exist_ok=True)
        _ = (skills_dir / op / "SKILL.md").write_text(
            _present_body(op=op, script=script), encoding="utf-8"
        )

    for op in _PRESENT_PROSE_OPS:
        (skills_dir / op).mkdir(parents=True, exist_ok=True)
        _ = (skills_dir / op / "SKILL.md").write_text(_present_prose_body(op=op), encoding="utf-8")


@pytest.fixture(autouse=True)
def point_at(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Build a valid surface under tmp_path and repoint the check's constants.

    Autouse so EVERY test starts from a valid surface; tests that need the
    fake repo root request `point_at` by name to receive `tmp_path`.
    """
    monkeypatch.chdir(tmp_path)
    _write_surface(root=tmp_path)
    claude_dir = tmp_path / ".claude-plugin"
    codex_dir = claude_dir / ".codex-plugin"
    monkeypatch.setattr(_CHECK, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        _CHECK, "_MARKETPLACE", tmp_path / ".agents" / "plugins" / "marketplace.json"
    )
    monkeypatch.setattr(_CHECK, "_CLAUDE_DIR", claude_dir)
    monkeypatch.setattr(_CHECK, "_CLAUDE_MANIFEST", claude_dir / "plugin.json")
    monkeypatch.setattr(_CHECK, "_CODEX_DIR", codex_dir)
    monkeypatch.setattr(_CHECK, "_CODEX_MANIFEST", codex_dir / "plugin.json")
    monkeypatch.setattr(_CHECK, "_SKILLS_DIR", codex_dir / "skills")
    return tmp_path


def _market(*, root: Path) -> Path:
    return root / ".agents" / "plugins" / "marketplace.json"


def _codex_manifest(*, root: Path) -> Path:
    return root / ".claude-plugin" / ".codex-plugin" / "plugin.json"


def _skills_dir(*, root: Path) -> Path:
    return root / ".claude-plugin" / ".codex-plugin" / "skills"


def _skill(*, root: Path, op: str) -> Path:
    return _skills_dir(root=root) / op / "SKILL.md"


def _live_next_skill() -> Path:
    return _REPO_ROOT / ".claude-plugin" / ".codex-plugin" / "skills" / "next" / "SKILL.md"


def _rewrite_json(*, path: Path, mutate: object) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert callable(mutate)
    mutate(data)
    _ = path.write_text(json.dumps(data), encoding="utf-8")


def _extract_resolution_script(*, skill: Path) -> str:
    text = skill.read_text(encoding="utf-8")
    start = text.index('PLUGIN_ROOT="$LIVESPEC_ORCH_PLUGIN_ROOT"')
    end = text.index('if [ -z "$PLUGIN_ROOT" ] || [ ! -d "$PLUGIN_ROOT/scripts/bin" ]; then')
    return text[start:end] + 'printf "%s" "$PLUGIN_ROOT"\n'


def _write_fake_codex(*, bin_dir: Path, installed_root: Path) -> None:
    bin_dir.mkdir(parents=True)
    codex = bin_dir / "codex"
    _ = codex.write_text(
        "#!/usr/bin/env bash\n"
        "cat <<JSON\n"
        '{"installed":[{"pluginId":"'
        f"{_PLUGIN_NAME}@{_PLUGIN_NAME}"
        '","source":{"path":"'
        f"{installed_root}"
        '"}}]}\n'
        "JSON\n",
        encoding="utf-8",
    )
    codex.chmod(0o755)


def _write_plugin_candidate(*, root: Path, name: str, with_orchestrator_wrapper: bool) -> None:
    plugin_root = root / ".claude-plugin"
    bin_dir = plugin_root / "scripts" / "bin"
    bin_dir.mkdir(parents=True)
    _ = (plugin_root / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    if with_orchestrator_wrapper:
        _ = (bin_dir / "drive.py").write_text("# wrapper\n", encoding="utf-8")


def _resolve_skill_root(*, skill: Path, cwd: Path, fake_bin: Path) -> str:
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env.pop("LIVESPEC_ORCH_PLUGIN_ROOT", None)
    result = subprocess.run(
        ["bash", "-c", _extract_resolution_script(skill=skill)],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


# --------------------------------------------------------------------------
# Happy path.
# --------------------------------------------------------------------------


def test_valid_surface_passes() -> None:
    assert _CHECK.main() == 0


def test_present_set_is_the_six_thin_ops() -> None:
    assert set(_CHECK._PRESENT_OPS) == set(_PRESENT_OPS)  # noqa: SLF001


def test_present_prose_set_is_the_six_heavyweight_ops() -> None:
    assert frozenset(_PRESENT_PROSE_OPS) == _CHECK._PRESENT_PROSE_OPS  # noqa: SLF001


def test_pending_set_is_empty() -> None:
    """The P3b extraction is complete: no heavyweight op remains pending."""
    assert frozenset(_PENDING_OPS) == _CHECK._PENDING_CODEX_OPS  # noqa: SLF001
    assert frozenset() == _CHECK._PENDING_CODEX_OPS  # noqa: SLF001


def test_codex_resolution_skips_core_like_cwd(tmp_path: Path) -> None:
    core_like = tmp_path / "core-like"
    installed_root = tmp_path / "installed"
    fake_bin = tmp_path / "bin"
    (installed_root / "scripts" / "bin").mkdir(parents=True)
    _write_plugin_candidate(root=core_like, name="livespec", with_orchestrator_wrapper=False)
    _write_fake_codex(bin_dir=fake_bin, installed_root=installed_root)

    resolved = _resolve_skill_root(
        skill=_live_next_skill(),
        cwd=core_like,
        fake_bin=fake_bin,
    )

    assert resolved == str(installed_root)


def test_codex_resolution_accepts_orchestrator_plugin_cwd(tmp_path: Path) -> None:
    orchestrator_like = tmp_path / "orchestrator-like"
    installed_root = tmp_path / "installed"
    fake_bin = tmp_path / "bin"
    (installed_root / "scripts" / "bin").mkdir(parents=True)
    _write_plugin_candidate(
        root=orchestrator_like,
        name=_PLUGIN_NAME,
        with_orchestrator_wrapper=True,
    )
    _write_fake_codex(bin_dir=fake_bin, installed_root=installed_root)

    resolved = _resolve_skill_root(
        skill=_live_next_skill(),
        cwd=orchestrator_like,
        fake_bin=fake_bin,
    )

    assert resolved == str(orchestrator_like / ".claude-plugin")


# --------------------------------------------------------------------------
# Marketplace catalog.
# --------------------------------------------------------------------------


def test_marketplace_wrong_name_fails(point_at: Path) -> None:
    _rewrite_json(path=_market(root=point_at), mutate=lambda d: d.update({"name": "wrong"}))
    assert _CHECK.main() == 1


def test_marketplace_two_plugins_fails(point_at: Path) -> None:
    def _dup(d: dict[str, object]) -> None:
        plugins = d["plugins"]
        assert isinstance(plugins, list)
        plugins.append(dict(plugins[0]))

    _rewrite_json(path=_market(root=point_at), mutate=_dup)
    assert _CHECK.main() == 1


def test_marketplace_wrong_source_fails(point_at: Path) -> None:
    def _bad_source(d: dict[str, object]) -> None:
        plugins = d["plugins"]
        assert isinstance(plugins, list)
        plugins[0]["source"] = {"source": "local", "path": "./codex"}

    _rewrite_json(path=_market(root=point_at), mutate=_bad_source)
    assert _CHECK.main() == 1


def test_marketplace_description_drift_fails(point_at: Path) -> None:
    def _drift(d: dict[str, object]) -> None:
        plugins = d["plugins"]
        assert isinstance(plugins, list)
        plugins[0]["description"] = "drifted"

    _rewrite_json(path=_market(root=point_at), mutate=_drift)
    assert _CHECK.main() == 1


def test_marketplace_unreadable_fails(point_at: Path) -> None:
    _ = _market(root=point_at).write_text("{ not json ", encoding="utf-8")
    assert _CHECK.main() == 1


def test_marketplace_plugins_not_a_list_fails(point_at: Path) -> None:
    _rewrite_json(path=_market(root=point_at), mutate=lambda d: d.update({"plugins": {}}))
    assert _CHECK.main() == 1


def test_marketplace_entry_wrong_name_fails(point_at: Path) -> None:
    def _bad_entry_name(d: dict[str, object]) -> None:
        plugins = d["plugins"]
        assert isinstance(plugins, list)
        plugins[0]["name"] = "other"

    _rewrite_json(path=_market(root=point_at), mutate=_bad_entry_name)
    assert _CHECK.main() == 1


def test_marketplace_entry_non_dict_fails(point_at: Path) -> None:
    _rewrite_json(path=_market(root=point_at), mutate=lambda d: d.update({"plugins": ["x"]}))
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Codex manifest.
# --------------------------------------------------------------------------


def test_manifest_wrong_name_fails(point_at: Path) -> None:
    _rewrite_json(path=_codex_manifest(root=point_at), mutate=lambda d: d.update({"name": "x"}))
    assert _CHECK.main() == 1


def test_manifest_version_drift_fails(point_at: Path) -> None:
    _rewrite_json(
        path=_codex_manifest(root=point_at), mutate=lambda d: d.update({"version": "9.9.9"})
    )
    assert _CHECK.main() == 1


def test_manifest_wrong_skills_path_fails(point_at: Path) -> None:
    _rewrite_json(
        path=_codex_manifest(root=point_at), mutate=lambda d: d.update({"skills": "./skills/"})
    )
    assert _CHECK.main() == 1


def test_manifest_description_drift_fails(point_at: Path) -> None:
    _rewrite_json(
        path=_codex_manifest(root=point_at), mutate=lambda d: d.update({"description": "x"})
    )
    assert _CHECK.main() == 1


def test_manifest_with_hooks_key_fails(point_at: Path) -> None:
    _rewrite_json(
        path=_codex_manifest(root=point_at),
        mutate=lambda d: d.update({"hooks": "./hooks/hooks.json"}),
    )
    assert _CHECK.main() == 1


def test_manifest_unreadable_fails(point_at: Path) -> None:
    _ = _codex_manifest(root=point_at).write_text("nope", encoding="utf-8")
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Hooks-dir absence (the no-guard contract).
# --------------------------------------------------------------------------


def test_codex_hooks_dir_present_fails(point_at: Path) -> None:
    (_point_at_codex(root=point_at) / "hooks").mkdir(parents=True)
    assert _CHECK.main() == 1


def _point_at_codex(*, root: Path) -> Path:
    return root / ".claude-plugin" / ".codex-plugin"


# --------------------------------------------------------------------------
# Skill set membership.
# --------------------------------------------------------------------------


def test_missing_present_skill_dir_fails(point_at: Path) -> None:
    import shutil

    shutil.rmtree(_skills_dir(root=point_at) / "next")
    assert _CHECK.main() == 1


def test_extra_skill_dir_fails(point_at: Path) -> None:
    (_skills_dir(root=point_at) / "bogus").mkdir()
    assert _CHECK.main() == 1


def test_pending_op_dir_present_fails(point_at: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The visibility mechanism still fires: a pending op shipping a Codex dir fails.

    `_PENDING_CODEX_OPS` is empty now that the P3b extraction is complete, so
    this exercises the retained mechanism against a SYNTHETIC pending op:
    enumerate it as pending, ship its skill dir, and confirm the "must NOT ship
    yet" assertion still trips.
    """
    monkeypatch.setattr(_CHECK, "_PENDING_CODEX_OPS", frozenset({"future-op"}))
    (_skills_dir(root=point_at) / "future-op").mkdir()
    assert _CHECK.main() == 1


def test_missing_skills_dir_fails(point_at: Path) -> None:
    import shutil

    shutil.rmtree(_skills_dir(root=point_at))
    assert _CHECK.main() == 1


def test_skill_dir_without_skill_md_fails(point_at: Path) -> None:
    _skill(root=point_at, op="next").unlink()
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Frontmatter.
# --------------------------------------------------------------------------


def test_no_frontmatter_fails(point_at: Path) -> None:
    _ = _skill(root=point_at, op="next").write_text("no frontmatter here", encoding="utf-8")
    assert _CHECK.main() == 1


def test_frontmatter_name_mismatch_fails(point_at: Path) -> None:
    body = _skill(root=point_at, op="next").read_text(encoding="utf-8")
    _ = _skill(root=point_at, op="next").write_text(
        body.replace("name: next", "name: other"), encoding="utf-8"
    )
    assert _CHECK.main() == 1


def test_frontmatter_empty_description_fails(point_at: Path) -> None:
    _ = _skill(root=point_at, op="next").write_text(
        "---\nname: next\ndescription:\n---\n\n"
        + _RESOLUTION_BLOCK
        + '```bash\npython3 "$PLUGIN_ROOT/scripts/bin/next.py" "$@"\n```\n',
        encoding="utf-8",
    )
    assert _CHECK.main() == 1


def test_frontmatter_allowed_tools_fails(point_at: Path) -> None:
    body = _skill(root=point_at, op="next").read_text(encoding="utf-8")
    _ = _skill(root=point_at, op="next").write_text(
        body.replace("description: Thin Codex binding for next.", "allowed-tools: Bash"),
        encoding="utf-8",
    )
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Body markers.
# --------------------------------------------------------------------------


def test_missing_resolution_snippet_fails(point_at: Path) -> None:
    body = _skill(root=point_at, op="next").read_text(encoding="utf-8")
    _ = _skill(root=point_at, op="next").write_text(
        body.replace(f"codex plugin list --json -m {_PLUGIN_NAME}", "echo hi"), encoding="utf-8"
    )
    assert _CHECK.main() == 1


def test_missing_plugin_root_var_fails(point_at: Path) -> None:
    body = _skill(root=point_at, op="next").read_text(encoding="utf-8")
    _ = _skill(root=point_at, op="next").write_text(
        body.replace("$PLUGIN_ROOT", "$OTHER_ROOT"), encoding="utf-8"
    )
    assert _CHECK.main() == 1


def test_missing_wrapper_self_invocation_fails(point_at: Path) -> None:
    _ = _skill(root=point_at, op="next").write_text(
        "---\nname: next\ndescription: x\n---\n\n"
        + _RESOLUTION_BLOCK
        + 'echo "$PLUGIN_ROOT" with no wrapper invocation\n',
        encoding="utf-8",
    )
    assert _CHECK.main() == 1


def test_live_claude_token_fails(point_at: Path) -> None:
    body = _skill(root=point_at, op="next").read_text(encoding="utf-8")
    token = "${CLAUDE_PLUGIN" + "_ROOT}"
    _ = _skill(root=point_at, op="next").write_text(
        body.replace(
            'python3 "$PLUGIN_ROOT/scripts/bin/next.py"', f'python3 "{token}/scripts/bin/next.py"'
        ),
        encoding="utf-8",
    )
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Prose-backed capture ops.
# --------------------------------------------------------------------------


def test_prose_op_without_prose_read_fails(point_at: Path) -> None:
    """A prose-backed capture op whose body never reads its prose/<op>.md fails."""
    op = "capture-work-item"
    _ = _skill(root=point_at, op=op).write_text(
        f"---\nname: {op}\ndescription: x\n---\n\n"
        + _RESOLUTION_BLOCK
        + '```bash\necho "$PLUGIN_ROOT has no prose read"\n```\n',
        encoding="utf-8",
    )
    assert _CHECK.main() == 1


def test_prose_op_missing_resolution_snippet_fails(point_at: Path) -> None:
    op = "capture-impl-gaps"
    body = _skill(root=point_at, op=op).read_text(encoding="utf-8")
    _ = _skill(root=point_at, op=op).write_text(
        body.replace(f"codex plugin list --json -m {_PLUGIN_NAME}", "echo hi"), encoding="utf-8"
    )
    assert _CHECK.main() == 1


def test_prose_op_live_claude_token_fails(point_at: Path) -> None:
    op = "capture-spec-drift"
    body = _skill(root=point_at, op=op).read_text(encoding="utf-8")
    token = "${CLAUDE_PLUGIN" + "_ROOT}"
    _ = _skill(root=point_at, op=op).write_text(
        body.replace('cat "$PLUGIN_ROOT/prose/', f'cat "{token}/prose/'),
        encoding="utf-8",
    )
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Fenced invocation idiom.
# --------------------------------------------------------------------------


def test_fenced_uv_run_fails(point_at: Path) -> None:
    _ = _skill(root=point_at, op="next").write_text(
        "---\nname: next\ndescription: x\n---\n\n"
        + _RESOLUTION_BLOCK
        + '```bash\nuv run python "$PLUGIN_ROOT/scripts/bin/next.py"\n```\n',
        encoding="utf-8",
    )
    assert _CHECK.main() == 1


def test_fenced_literal_claude_plugin_path_fails(point_at: Path) -> None:
    _ = _skill(root=point_at, op="next").write_text(
        "---\nname: next\ndescription: x\n---\n\n"
        + _RESOLUTION_BLOCK
        + '```bash\npython3 ".claude-plugin/scripts/bin/next.py"\n```\n',
        encoding="utf-8",
    )
    assert _CHECK.main() == 1


def test_fenced_claude_token_in_invocation_fails(point_at: Path) -> None:
    token = "${CLAUDE_PLUGIN" + "_ROOT}"
    _ = _skill(root=point_at, op="next").write_text(
        "---\nname: next\ndescription: x\n---\n\n"
        + _RESOLUTION_BLOCK
        + f'```bash\npython3 "{token}/scripts/bin/next.py"\n```\n',
        encoding="utf-8",
    )
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Helper-level coverage.
# --------------------------------------------------------------------------


def test_frontmatter_block_none_for_empty() -> None:
    assert _CHECK._frontmatter_block(text="") is None  # noqa: SLF001


def test_frontmatter_block_none_for_unterminated() -> None:
    assert _CHECK._frontmatter_block(text="---\nname: x\nbody") is None  # noqa: SLF001


def test_str_field_returns_value_for_str() -> None:
    assert _CHECK._str_field(parsed={"k": "v"}, key="k") == "v"  # noqa: SLF001


def test_str_field_none_for_non_str_value() -> None:
    """A dict whose key holds a non-str value yields None (not the raw value)."""
    assert _CHECK._str_field(parsed={"k": 7}, key="k") is None  # noqa: SLF001


def test_str_field_none_for_non_dict() -> None:
    assert _CHECK._str_field(parsed=["not", "a", "dict"], key="k") is None  # noqa: SLF001


def test_module_main_is_callable() -> None:
    assert callable(_CHECK.main)
