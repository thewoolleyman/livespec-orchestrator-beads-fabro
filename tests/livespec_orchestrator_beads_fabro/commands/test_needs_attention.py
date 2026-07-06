"""Tests for the needs-attention thin binding."""

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.needs_attention import (
    build_attention,
    main,
    render_json,
    render_markdown,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
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


def test_build_attention_composes_impl_human_valves_plan_threads_and_spec_next(tmp_path) -> None:
    _write_config(tmp_path)
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
        "spec:next:SPECIFICATION",
        "plan:needs-attention",
    ]
    assert attention[0].handoff.action_id == "approve:bd-approval"
    assert attention[1].handoff.command.endswith("--action accept:bd-accept --json")
    assert attention[3].handoff.command.endswith("--action impl:bd-ready --json")
    assert attention[-1].source_ref.path == "plan/needs-attention/"


def test_render_json_wraps_flat_attention_array(tmp_path) -> None:
    _write_config(tmp_path)
    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    payload = json.loads(render_json(attention=attention))

    assert list(payload) == ["attention"]
    assert payload["attention"][0]["id"] == "spec:next:SPECIFICATION"


def test_render_markdown_lists_handoff_commands(tmp_path) -> None:
    _write_config(tmp_path)
    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    rendered = render_markdown(attention=attention)

    assert rendered.startswith("# Needs Attention\n")
    assert "`spec:next:SPECIFICATION`" in rendered
    assert "codex exec livespec:next" in rendered


def test_render_markdown_empty_attention() -> None:
    assert render_markdown(attention=[]) == "No attention items.\n"


def test_main_json_output(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(tmp_path)
    rc = main(["--json", "--skip-hygiene", "--project-root", str(tmp_path), "--repo-name", "repo"])

    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["attention"][0]["id"] == "spec:next:SPECIFICATION"


def test_main_markdown_output(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(tmp_path)
    rc = main(["--skip-hygiene", "--project-root", str(tmp_path), "--repo-name", "repo"])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.startswith("# Needs Attention\n")
