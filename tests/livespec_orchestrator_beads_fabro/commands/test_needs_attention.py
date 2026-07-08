"""Tests for the needs-attention thin binding."""

import json
import shlex
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands.needs_attention import (
    CoreRootBases,
    SpecNextSeam,
    _adapt_top_candidate,
    _candidate_urgency,
    _claude_installed_core_roots,
    _codex_installed_core_roots,
    _read_spec_clis_next_argv,
    _resolve_core_plugin_root,
    _resolve_spec_next_command,
    _spec_next,
    _spec_output_from_candidate,
    _SpecNextResult,
    build_attention,
    main,
    render_json,
    render_markdown,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.needs_attention import SpecNextOutput


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed(item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)


def _write_config(project_root: Path) -> None:
    (project_root / ".livespec.jsonc").write_text(
        """{
  \"livespec-orchestrator-beads-fabro\": {
    \"connection\": {
      \"tenant\": \"livespec-impl-beads\",
      \"prefix\": \"bd\",
      \"server_user\": \"livespec-impl-beads\",
      \"database\": \"livespec-impl-beads\",
      \"bd_path\": \"bd\",
      \"fake\": true
    }
  }
}
""",
        encoding="utf-8",
    )


def _stub_spec_output() -> SpecNextOutput:
    """A deterministic spec-`next` adaptation used to keep composition tests hermetic."""
    return SpecNextOutput(
        op="revise",
        spec_target="SPECIFICATION",
        summary="Revise a pending proposed change.",
        command="codex exec livespec:revise --project-root /workspace/livespec",
        urgency="medium",
    )


def _stub_spec_next(monkeypatch: pytest.MonkeyPatch, *, output: SpecNextOutput | None) -> None:
    """Replace `_spec_next` so `build_attention` never touches a live CORE checkout."""

    def _fake(*, project_root: Path) -> SpecNextOutput | None:
        _ = project_root
        return output

    monkeypatch.setattr(needs_attention, "_spec_next", _fake)


def _seam(
    *,
    command: list[str] | None,
    result: _SpecNextResult | None = None,
    raises: Exception | None = None,
    calls: dict[str, object] | None = None,
) -> SpecNextSeam:
    """Build an injectable spec-`next` seam with a fake resolver + runner."""

    def _resolve(*, project_root: Path) -> list[str] | None:
        _ = project_root
        return command

    def _run(*, argv: list[str]) -> _SpecNextResult:
        if calls is not None:
            calls["argv"] = argv
            calls["run"] = True
        if raises is not None:
            raise raises
        assert result is not None
        return result

    return SpecNextSeam(resolve_command=_resolve, run=_run)


def _item(
    *,
    id_: str,
    status: str,
    rank: str = "a2",
    blocked_reason: str | None = None,
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title=f"{id_} title",
        description="d",
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=blocked_reason,  # type: ignore[arg-type]
    )


def test_build_attention_composes_impl_human_valves_plan_threads_and_spec_next(
    tmp_path, monkeypatch
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=_stub_spec_output())
    _ = (tmp_path / "plan" / "needs-attention").mkdir(parents=True)
    _seed(_item(id_="bd-ready", status="ready", rank="a1"))
    _seed(_item(id_="bd-approval", status="pending-approval", rank="a2"))
    _seed(_item(id_="bd-accept", status="acceptance", rank="a3"))
    _seed(_item(id_="bd-block", status="blocked", rank="a4", blocked_reason="needs-human"))

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [item.id for item in attention] == [
        "valve:approve:bd-approval",
        "valve:accept:bd-accept",
        "valve:set-admission:bd-block",
        "impl:bd-ready",
        "spec:revise:SPECIFICATION",
        "plan:needs-attention",
    ]
    assert attention[0].handoff.action_id == "approve:bd-approval"
    assert attention[1].handoff.command.endswith("--action accept:bd-accept --json")
    assert attention[3].handoff.command.endswith("--action impl:bd-ready --json")
    assert attention[-1].source_ref.path == "plan/needs-attention/"


def test_build_attention_drops_spec_item_when_spec_next_none(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [item.kind for item in attention if item.kind == "spec"] == []


def test_render_json_wraps_flat_attention_array(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=_stub_spec_output())
    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    payload = json.loads(render_json(attention=attention))

    assert list(payload) == ["attention"]
    assert payload["attention"][0]["id"] == "spec:revise:SPECIFICATION"


def test_render_markdown_lists_handoff_commands(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=_stub_spec_output())
    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    rendered = render_markdown(attention=attention)

    assert rendered.startswith("# Needs Attention\n")
    assert "`spec:revise:SPECIFICATION`" in rendered
    assert "codex exec livespec:revise" in rendered


def test_render_markdown_empty_attention() -> None:
    assert render_markdown(attention=[]) == "No attention items.\n"


def test_main_json_output(
    tmp_path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=_stub_spec_output())
    rc = main(["--json", "--skip-hygiene", "--project-root", str(tmp_path), "--repo-name", "repo"])

    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["attention"][0]["id"] == "spec:revise:SPECIFICATION"


def test_main_markdown_output(
    tmp_path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=_stub_spec_output())
    rc = main(["--skip-hygiene", "--project-root", str(tmp_path), "--repo-name", "repo"])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.startswith("# Needs Attention\n")


# --------------------------------------------------------------------------
# `_spec_next` — invoke CORE spec-`next` cross-plane via an injected seam,
# adapt the top candidate, and fail soft (never emit a pointer).
# --------------------------------------------------------------------------


def test_spec_next_inlines_top_actionable_candidate(tmp_path) -> None:
    stdout = json.dumps(
        {
            "candidates": [
                {
                    "action": "revise",
                    "reason": "proposed change pending; queue depth 1",
                    "urgency": "high",
                    "target": "proposed_changes/owned-heading-coverage-todos.md",
                },
                {"action": "prune-history", "reason": "many versions", "urgency": "low"},
            ]
        }
    )
    calls: dict[str, object] = {}
    seam = _seam(
        command=["python3", "/core/scripts/bin/next.py"],
        result=_SpecNextResult(stdout=stdout, returncode=0),
        calls=calls,
    )

    output = _spec_next(project_root=tmp_path, seam=seam)

    assert output is not None
    assert output.op == "revise"
    assert output.spec_target == "proposed_changes/owned-heading-coverage-todos.md"
    assert output.summary == "proposed change pending; queue depth 1"
    assert output.urgency == "high"
    assert output.command == (
        f"codex exec livespec:revise --project-root {shlex.quote(str(tmp_path))}"
    )
    assert calls["argv"] == [
        "python3",
        "/core/scripts/bin/next.py",
        "--project-root",
        str(tmp_path),
    ]


def test_spec_next_returns_none_when_candidates_empty(tmp_path) -> None:
    seam = _seam(
        command=["python3", "/core/next.py"],
        result=_SpecNextResult(stdout=json.dumps({"candidates": []}), returncode=0),
    )
    assert _spec_next(project_root=tmp_path, seam=seam) is None


def test_spec_next_returns_none_when_seam_run_raises(tmp_path) -> None:
    import subprocess

    seam = _seam(
        command=["python3", "/core/next.py"],
        raises=subprocess.SubprocessError("boom"),
    )
    assert _spec_next(project_root=tmp_path, seam=seam) is None


def test_spec_next_returns_none_when_cli_exits_nonzero(tmp_path) -> None:
    seam = _seam(
        command=["python3", "/core/next.py"],
        result=_SpecNextResult(stdout="", returncode=2),
    )
    assert _spec_next(project_root=tmp_path, seam=seam) is None


def test_spec_next_returns_none_when_stdout_unparseable(tmp_path) -> None:
    seam = _seam(
        command=["python3", "/core/next.py"],
        result=_SpecNextResult(stdout="not json at all", returncode=0),
    )
    assert _spec_next(project_root=tmp_path, seam=seam) is None


def test_spec_next_does_not_run_cli_when_unresolvable(tmp_path) -> None:
    calls: dict[str, object] = {}
    seam = _seam(command=None, result=_SpecNextResult(stdout="{}", returncode=0), calls=calls)

    assert _spec_next(project_root=tmp_path, seam=seam) is None
    assert "run" not in calls


# --------------------------------------------------------------------------
# Pure candidate-adaptation helpers.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("high", "high"), ("low", "low"), ("medium", "medium"), ("bogus", "medium"), (None, "medium")],
)
def test_candidate_urgency(value: object, expected: str) -> None:
    assert _candidate_urgency(value=value) == expected


def test_spec_output_from_candidate_non_dict_returns_none(tmp_path) -> None:
    assert _spec_output_from_candidate(candidate="x", project_root=tmp_path) is None


def test_spec_output_from_candidate_missing_action_returns_none(tmp_path) -> None:
    assert _spec_output_from_candidate(candidate={"reason": "r"}, project_root=tmp_path) is None


def test_spec_output_from_candidate_defaults_summary_and_target(tmp_path) -> None:
    output = _spec_output_from_candidate(candidate={"action": "critique"}, project_root=tmp_path)
    assert output is not None
    assert output.summary == "Spec-side critique is ready."
    assert output.spec_target == "SPECIFICATION"
    assert output.urgency == "medium"
    assert output.command == (
        f"codex exec livespec:critique --project-root {shlex.quote(str(tmp_path))}"
    )


def test_spec_output_from_candidate_empty_reason_and_target_default(tmp_path) -> None:
    output = _spec_output_from_candidate(
        candidate={"action": "revise", "reason": "", "target": ""}, project_root=tmp_path
    )
    assert output is not None
    assert output.summary == "Spec-side revise is ready."
    assert output.spec_target == "SPECIFICATION"


def test_adapt_top_candidate_non_object_payload_returns_none(tmp_path) -> None:
    assert _adapt_top_candidate(stdout='"a string"', project_root=tmp_path) is None


def test_adapt_top_candidate_candidates_not_list_returns_none(tmp_path) -> None:
    assert _adapt_top_candidate(stdout='{"candidates": {}}', project_root=tmp_path) is None


def test_adapt_top_candidate_skips_inert_then_selects_actionable(tmp_path) -> None:
    stdout = json.dumps(
        {
            "candidates": [
                "not-a-dict",
                {"action": "none", "reason": "nothing"},
                {"action": "propose-change", "reason": "gap found", "urgency": "medium"},
            ]
        }
    )
    output = _adapt_top_candidate(stdout=stdout, project_root=tmp_path)
    assert output is not None
    assert output.op == "propose-change"


# --------------------------------------------------------------------------
# CORE plugin-root resolution tiers — driven by injected `CoreRootBases` (tmp
# dirs only; NO real ~/.claude or ~/.codex, NO HOME monkeypatching).
# --------------------------------------------------------------------------


def _plant_next(root: Path) -> Path:
    """Materialize `<root>/scripts/bin/next.py` so `root` resolves as a CORE root."""
    (root / "scripts" / "bin").mkdir(parents=True)
    _ = (root / "scripts" / "bin" / "next.py").write_text("# core next\n", encoding="utf-8")
    return root


def _empty_bases(tmp_path: Path) -> CoreRootBases:
    """Bases that resolve nothing (both cache tiers point at non-existent tmp paths)."""
    return CoreRootBases(
        claude_registry=tmp_path / "no-claude" / "installed_plugins.json",
        codex_cache=tmp_path / "no-codex-cache",
    )


def test_resolve_core_root_prefers_fleet_sibling(tmp_path) -> None:
    workspace = tmp_path / "ws"
    sibling = _plant_next(workspace / "livespec" / ".claude-plugin")
    project = workspace / "governed"
    project.mkdir(parents=True)

    assert _resolve_core_plugin_root(project_root=project, bases=_empty_bases(tmp_path)) == sibling


def test_resolve_core_root_uses_claude_installed_cache(tmp_path) -> None:
    core = _plant_next(tmp_path / "claude-cache" / "livespec")
    registry = tmp_path / "installed_plugins.json"
    _ = registry.write_text(
        json.dumps({"plugins": {"livespec@livespec": [{"installPath": str(core)}]}}),
        encoding="utf-8",
    )
    bases = CoreRootBases(claude_registry=registry, codex_cache=tmp_path / "no-codex")
    project = tmp_path / "governed"
    project.mkdir()

    assert _resolve_core_plugin_root(project_root=project, bases=bases) == core


def test_resolve_core_root_uses_codex_installed_cache(tmp_path) -> None:
    # Codex-only user WITHOUT a fleet sibling and WITHOUT a Claude registry: the
    # Codex-cache tier must resolve `<cache>/livespec/livespec/<version>` — the
    # regression the pre-Codex-tier resolver silently dropped.
    codex_cache = tmp_path / "codex-cache"
    core = _plant_next(codex_cache / "livespec" / "livespec" / "0.7.1")
    bases = CoreRootBases(claude_registry=tmp_path / "missing.json", codex_cache=codex_cache)
    project = tmp_path / "governed"
    project.mkdir()

    assert _resolve_core_plugin_root(project_root=project, bases=bases) == core


def test_resolve_core_root_codex_cache_picks_highest_version(tmp_path) -> None:
    codex_cache = tmp_path / "codex-cache"
    _ = _plant_next(codex_cache / "livespec" / "livespec" / "0.7.1")
    highest = _plant_next(codex_cache / "livespec" / "livespec" / "0.10.0")
    (codex_cache / "livespec" / "livespec" / "main").mkdir()  # non-numeric sorts lowest
    bases = CoreRootBases(claude_registry=tmp_path / "missing.json", codex_cache=codex_cache)
    project = tmp_path / "governed"
    project.mkdir()

    assert _resolve_core_plugin_root(project_root=project, bases=bases) == highest


def test_resolve_core_root_none_when_all_tiers_miss(tmp_path) -> None:
    project = tmp_path / "governed"
    project.mkdir()

    assert _resolve_core_plugin_root(project_root=project, bases=_empty_bases(tmp_path)) is None


def test_claude_installed_core_roots_missing_registry(tmp_path) -> None:
    assert list(_claude_installed_core_roots(registry=tmp_path / "nope.json")) == []


@pytest.mark.parametrize(
    "registry_text",
    [
        "{ not json",
        json.dumps([1, 2]),
        json.dumps({}),
        json.dumps({"plugins": "x"}),
        json.dumps({"plugins": {"livespec@livespec": "x"}}),
        json.dumps({"plugins": {"livespec@livespec": ["str", {"installPath": ""}, {"x": 1}]}}),
    ],
)
def test_claude_installed_core_roots_malformed_yields_nothing(tmp_path, registry_text: str) -> None:
    registry = tmp_path / "installed_plugins.json"
    _ = registry.write_text(registry_text, encoding="utf-8")
    assert list(_claude_installed_core_roots(registry=registry)) == []


def test_claude_installed_core_roots_yields_install_paths(tmp_path) -> None:
    registry = tmp_path / "installed_plugins.json"
    _ = registry.write_text(
        json.dumps(
            {"plugins": {"livespec@livespec": [{"installPath": "/a"}, {"installPath": "/b"}]}}
        ),
        encoding="utf-8",
    )
    assert list(_claude_installed_core_roots(registry=registry)) == [Path("/a"), Path("/b")]


def test_codex_installed_core_roots_missing_plugin_dir(tmp_path) -> None:
    assert list(_codex_installed_core_roots(cache=tmp_path / "empty-cache")) == []


def test_codex_installed_core_roots_yields_version_dirs_highest_first(tmp_path) -> None:
    base = tmp_path / "cache" / "livespec" / "livespec"
    (base / "0.7.1").mkdir(parents=True)
    (base / "0.10.0").mkdir()

    roots = list(_codex_installed_core_roots(cache=tmp_path / "cache"))

    assert roots == [base / "0.10.0", base / "0.7.1"]


def test_read_spec_clis_next_argv_missing_file(tmp_path) -> None:
    assert _read_spec_clis_next_argv(project_root=tmp_path) is None


@pytest.mark.parametrize(
    "body",
    [
        "{ not valid jsonc",
        '"a string"',
        "{}",
        '{"spec_clis": "x"}',
        '{"spec_clis": {"next": "x"}}',
        '{"spec_clis": {"next": []}}',
        '{"spec_clis": {"next": [1, 2]}}',
    ],
)
def test_read_spec_clis_next_argv_off_happy_path_returns_none(tmp_path, body: str) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(body, encoding="utf-8")
    assert _read_spec_clis_next_argv(project_root=tmp_path) is None


def test_read_spec_clis_next_argv_returns_configured_argv(tmp_path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"spec_clis": {"next": ["python3", "/abs/next.py"]}}', encoding="utf-8"
    )
    assert _read_spec_clis_next_argv(project_root=tmp_path) == ["python3", "/abs/next.py"]


def test_resolve_spec_next_command_none_when_core_unresolvable(tmp_path) -> None:
    project = tmp_path / "governed"
    project.mkdir()
    assert _resolve_spec_next_command(project_root=project, bases=_empty_bases(tmp_path)) is None


def test_resolve_spec_next_command_substitutes_default_template(tmp_path) -> None:
    workspace = tmp_path / "ws"
    sibling = _plant_next(workspace / "livespec" / ".claude-plugin")
    project = workspace / "governed"
    project.mkdir(parents=True)

    command = _resolve_spec_next_command(project_root=project, bases=_empty_bases(tmp_path))

    assert command == ["python3", f"{sibling}/scripts/bin/next.py"]


def test_resolve_spec_next_command_uses_configured_argv(tmp_path) -> None:
    workspace = tmp_path / "ws"
    sibling = _plant_next(workspace / "livespec" / ".claude-plugin")
    project = workspace / "governed"
    project.mkdir(parents=True)
    _ = (project / ".livespec.jsonc").write_text(
        '{"spec_clis": {"next": ["python3", "${CLAUDE_PLUGIN_ROOT}/scripts/bin/next.py", "--x"]}}',
        encoding="utf-8",
    )

    command = _resolve_spec_next_command(project_root=project, bases=_empty_bases(tmp_path))

    assert command == ["python3", f"{sibling}/scripts/bin/next.py", "--x"]
