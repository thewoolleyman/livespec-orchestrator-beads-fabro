"""Tests for the needs-attention thin binding."""

import json
import shlex
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands.needs_attention import (
    SpecNextSeam,
    _spec_next,
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
    rc = main(
        argv=["--json", "--skip-hygiene", "--project-root", str(tmp_path), "--repo-name", "repo"]
    )

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
    rc = main(argv=["--skip-hygiene", "--project-root", str(tmp_path), "--repo-name", "repo"])

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
