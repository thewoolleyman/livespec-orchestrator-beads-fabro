"""Integration-tier acceptance for journal invoker attribution (contracts.md v073).

Drives the REAL `dispatcher.main(argv=["dispatch", ...])` CLI through the REAL
store/client seam against the in-memory `FakeBeadsClient`, with `run_dispatch`
replaced by a recording stand-in so no fabro run is launched. What is under
test is the ENVELOPE, not the dispatch: which identity every journaled record
carries, how that identity was resolved, and whether a tightened posture refuses
before anything is written.

The three resolution paths are exercised end to end rather than at the resolver,
because the resolver being right is not the claim — the claim is that the
identity the operator asserted is the one that reaches the file. The
`require_invoker` case additionally asserts the two things a "refused at startup"
guarantee actually means: no journal exists at all, and the item's stored status
is untouched.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_FLEET_MANIFEST_TEXT = (
    "// .livespec-fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)

_COMMITTED_WORKFLOW_TOML = (
    '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)

_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)

_EXIT_PRECONDITION_ERROR = 3


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment + fresh in-memory tenant per case.

    `LIVESPEC_INVOKER` is CLEARED here rather than per case: a stray value in
    the developer's own environment would silently turn a fallback case into an
    env case, which is exactly the distinction these tests exist to make.
    """
    scratch = tmp_path_factory.mktemp("fabro-invoker-attribution")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.delenv("LIVESPEC_INVOKER", raising=False)
    monkeypatch.setenv("USER", "cw")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-t1",
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        # A dispatchable fixture carries gradeable criteria: the entry-to-`ready`
        # and pre-dispatch walls (the effective-acceptance-criteria clause of contracts.md)
        # refuse an AI-dispositive item whose effective criteria parse to zero
        # gradeable assertions.
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _repo_with_workflow(*, tmp_path: Path, require_invoker: bool = False) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    dial = ', "dispatcher": {"require_invoker": true}' if require_invoker else ""
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": '
        f'{{"connection": {{"prefix": "bd-ib"}}{dial}}}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@dataclass(kw_only=True)
class _RecordingRunDispatch:
    calls: list[str] = field(default_factory=list)

    def __call__(self, **kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        self.calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=7,
            merge_sha="abc123",
            detail="merged",
        )


def _dispatch(
    *,
    repo: Path,
    workflow: Path,
    item_id: str,
    monkeypatch: pytest.MonkeyPatch,
    extra_argv: tuple[str, ...] = (),
) -> tuple[int, _RecordingRunDispatch]:
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item_id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
            *extra_argv,
        ]
    )
    return exit_code, recording


def test_the_flag_identity_reaches_every_journal_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--invoker` wins over `LIVESPEC_INVOKER` all the way to the file."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:should-lose")
    item = _item()
    append_work_item(path=_config(), item=item)

    exit_code, recording = _dispatch(
        repo=repo,
        workflow=workflow,
        item_id=item.id,
        monkeypatch=monkeypatch,
        extra_argv=("--invoker", "human:cw"),
    )

    assert exit_code == 0
    assert recording.calls == [item.id]
    records = _journal_records(repo=repo)
    assert records
    assert {record["invoker"] for record in records} == {"human:cw"}
    assert {record["invoker_source"] for record in records} == {"flag"}


def test_the_environment_identity_reaches_every_journal_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    monkeypatch.setenv("LIVESPEC_INVOKER", "foreman:seat-1")
    item = _item()
    append_work_item(path=_config(), item=item)

    exit_code, _ = _dispatch(repo=repo, workflow=workflow, item_id=item.id, monkeypatch=monkeypatch)

    assert exit_code == 0
    records = _journal_records(repo=repo)
    assert {record["invoker"] for record in records} == {"foreman:seat-1"}
    assert {record["invoker_source"] for record in records} == {"env"}


def test_an_unasserted_invocation_is_marked_never_trusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With neither input set and the dial off, the record carries the MARK."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)

    exit_code, _ = _dispatch(repo=repo, workflow=workflow, item_id=item.id, monkeypatch=monkeypatch)

    assert exit_code == 0
    records = _journal_records(repo=repo)
    assert {record["invoker_source"] for record in records} == {"fallback"}
    assert all(str(record["invoker"]).startswith("unattributed:cw@") for record in records)


def test_require_invoker_refuses_a_fallback_only_invocation_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, require_invoker=True)
    item = _item()
    append_work_item(path=_config(), item=item)

    exit_code, recording = _dispatch(
        repo=repo, workflow=workflow, item_id=item.id, monkeypatch=monkeypatch
    )

    assert exit_code == _EXIT_PRECONDITION_ERROR
    # No run created, no journal written, no store mutation: the three things
    # "refused at startup" is required to leave untouched.
    assert recording.calls == []
    assert not (repo / "tmp" / "fabro-dispatch-journal.jsonl").exists()
    assert _stored()[item.id].status == "ready"
    stderr = capsys.readouterr().err
    assert "--invoker" in stderr
    assert "LIVESPEC_INVOKER" in stderr


def test_require_invoker_admits_an_asserted_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dial refuses UNATTRIBUTED acts, not every act — the discriminating case."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, require_invoker=True)
    item = _item()
    append_work_item(path=_config(), item=item)

    exit_code, recording = _dispatch(
        repo=repo,
        workflow=workflow,
        item_id=item.id,
        monkeypatch=monkeypatch,
        extra_argv=("--invoker", "human:cw"),
    )

    assert exit_code == 0
    assert recording.calls == [item.id]
    assert {record["invoker_source"] for record in _journal_records(repo=repo)} == {"flag"}


def test_require_invoker_accepts_the_environment_as_an_assertion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, require_invoker=True)
    monkeypatch.setenv("LIVESPEC_INVOKER", "console:principal")
    item = _item()
    append_work_item(path=_config(), item=item)

    exit_code, recording = _dispatch(
        repo=repo, workflow=workflow, item_id=item.id, monkeypatch=monkeypatch
    )

    assert exit_code == 0
    assert recording.calls == [item.id]
    assert {record["invoker_source"] for record in _journal_records(repo=repo)} == {"env"}


def test_the_dial_is_absent_from_the_api_configurable_key_manifest(tmp_path: Path) -> None:
    """A dial that RELAXES attribution is not reachable over the API surface.

    Read through the drive `config-manifest` action — the surface a console
    actually consumes — rather than by importing the key table, so the
    assertion is about what is reachable rather than about how it is declared.
    """
    from livespec_orchestrator_beads_fabro.commands.drive import run_action

    repo = tmp_path / "repo"
    repo.mkdir()

    payload = run_action(repo=repo, action_id="config-manifest")

    manifest = payload["manifest"]
    keys = [entry["key"] for entry in manifest["keys"]]
    assert "require_invoker" not in keys
    assert "acceptance_rework_cap" in keys


def test_the_shipped_manifest_file_omits_the_dial() -> None:
    """The committed manifest artifact agrees with the served one."""
    manifest_path = (
        Path(__file__).resolve().parents[2] / ".claude-plugin" / "api-configurable-keys.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "require_invoker" not in [entry["key"] for entry in manifest["keys"]]
