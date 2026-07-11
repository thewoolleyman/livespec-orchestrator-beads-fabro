"""Tests for the fail-open ntfy alarm on terminal dispatcher failures.

Covers `_dispatcher_notify` (the reusable, fail-OPEN notifier) and its
wiring into `dispatcher._run_dispatch_command` / `_run_loop_command`. The
load-bearing invariant under test (0jxs operability gate): a notification
failure NEVER changes a dispatch verdict / exit code and NEVER blocks
exit. Credential hygiene is asserted directly: the body ships ONLY the
work-item id, the outcome class, and the run id — never the dispatch
`detail` blob, never an env value, never a credential-shaped URL.

No test makes a real network call: the notifier publishes through an
injected `NotifyPoster` fake, and the `main()`-driven wiring tests either
scrub the ntfy topic env (the silent no-op path) or monkeypatch
`HttpNotifyPoster` for a recording fake.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyEvent,
    notify_terminal,
    resolve_server,
    resolve_topic,
    terminal_events,
)

# Importing the module-private wiring helper directly (the test tier
# verifies the alarm wiring); importing it avoids the SLF001
# attribute-access ban while keeping the name addressable, the same
# pattern test_dispatcher_reflection uses for the reflection internals.
from livespec_orchestrator_beads_fabro.commands.dispatcher import (
    _alarm_on_terminal_failure,  # pyright: ignore[reportPrivateUsage]
)
from livespec_orchestrator_beads_fabro.store import append_work_item

# These names are re-exported from the shared dispatcher test module so the
# wiring tests reuse the exact hermetic harness (fake run_dispatch, repo +
# workflow scaffolding, the canned item / outcomes) without duplicating it.
from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher import (
    _FLEET_MANIFEST_TEXT,  # pyright: ignore[reportPrivateUsage]
    _config,  # pyright: ignore[reportPrivateUsage]
    _FakeRunDispatch,  # pyright: ignore[reportPrivateUsage]
    _green_outcome,  # pyright: ignore[reportPrivateUsage]
    _item,  # pyright: ignore[reportPrivateUsage]
    _repo_with_workflow,  # pyright: ignore[reportPrivateUsage]
)

_TOPIC_ENVS = ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER")


@pytest.fixture(autouse=True)
def _notify_test_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Hermetic env for every notify test.

    (1) No `main()`-driven test ever POSTs for real: the ntfy env is
    scrubbed so the default `HttpNotifyPoster` path resolves no topic
    (silent no-op); tests exercising a delivered POST set the env back
    explicitly and monkeypatch `HttpNotifyPoster` for a recording fake.
    (2) The dispatch credential + fleet-manifest preconditions are
    satisfied (the same hermetic C-mode setup `test_dispatcher` uses) so
    `main()` reaches the fake `run_dispatch` and the notify wiring.
    """
    for name in _TOPIC_ENVS:
        monkeypatch.delenv(name, raising=False)
    scratch = tmp_path_factory.mktemp("fabro-notify")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands.dispatcher._github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _RecordingPoster:
    """A `NotifyPoster` that records every POST and never touches the network."""

    result: bool = True
    raises: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    def post(self, *, url: str, body: str, title: str, timeout_seconds: float) -> bool:
        self.calls.append(
            {"url": url, "body": body, "title": title, "timeout_seconds": timeout_seconds}
        )
        if self.raises is not None:
            raise self.raises
        return self.result


def _outcome(*, work_item_id: str = "li-1", status: str = "failed") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        # A credential-bearing detail blob: it must NEVER reach the body.
        detail="boom https://x-access-token:ghp_SECRETSECRET@github.com/o/r.git",
    )


def _stages(*, journal: _RecordingJournal) -> list[object]:
    return [rec.get("stage") for rec in journal.records]


# --------------------------------------------------------------------------
# resolve_topic / resolve_server — env resolution
# --------------------------------------------------------------------------


def test_resolve_topic_prefers_dedicated_dispatcher_topic() -> None:
    env = {"CLAUDE_NTFY_DISPATCHER_TOPIC": "dispatch-alarms", "CLAUDE_NTFY_TOPIC": "general"}
    assert resolve_topic(environ=env) == "dispatch-alarms"


def test_resolve_topic_falls_back_to_shared_topic() -> None:
    assert resolve_topic(environ={"CLAUDE_NTFY_TOPIC": "general"}) == "general"


def test_resolve_topic_none_when_unset_or_empty() -> None:
    assert resolve_topic(environ={}) is None
    assert (
        resolve_topic(environ={"CLAUDE_NTFY_DISPATCHER_TOPIC": "", "CLAUDE_NTFY_TOPIC": ""}) is None
    )


def test_resolve_server_defaults_to_ntfy_sh() -> None:
    assert resolve_server(environ={}) == "https://ntfy.sh"


def test_resolve_server_override_trims_trailing_slash() -> None:
    assert resolve_server(environ={"CLAUDE_NTFY_SERVER": "https://ntfy.example/"}) == (
        "https://ntfy.example"
    )


# --------------------------------------------------------------------------
# terminal_events — leak-free event derivation
# --------------------------------------------------------------------------


def test_terminal_events_empty_for_all_green() -> None:
    greens = (_outcome(status="green"), _outcome(work_item_id="li-2", status="green"))
    assert terminal_events(outcomes=greens, include_loop_summary=True) == ()


def test_terminal_events_one_per_non_green_with_status_as_class() -> None:
    outcomes = (
        _outcome(work_item_id="li-1", status="failed"),
        _outcome(work_item_id="li-2", status="green"),
        _outcome(work_item_id="li-3", status="blocked"),
    )
    events = terminal_events(outcomes=outcomes, include_loop_summary=False)
    assert events == (
        NotifyEvent(work_item_id="li-1", outcome_class="failed"),
        NotifyEvent(work_item_id="li-3", outcome_class="blocked"),
    )


def test_terminal_events_appends_non_green_loop_summary_for_loop() -> None:
    outcomes = (_outcome(work_item_id="li-1", status="failed"),)
    events = terminal_events(outcomes=outcomes, include_loop_summary=True)
    assert events[-1] == NotifyEvent(work_item_id="(loop)", outcome_class="non-green-loop")


def test_terminal_events_no_loop_summary_when_all_green() -> None:
    greens = (_outcome(status="green"),)
    assert terminal_events(outcomes=greens, include_loop_summary=True) == ()


# --------------------------------------------------------------------------
# notify_terminal — POST shape + credential hygiene + fail-open
# --------------------------------------------------------------------------


def test_notify_terminal_noop_for_no_events() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    notify_terminal(
        events=(), run_id="r1", poster=poster, journal=journal, environ={"CLAUDE_NTFY_TOPIC": "t"}
    )
    assert poster.calls == []
    assert journal.records == []


def test_notify_terminal_skipped_when_no_topic() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    notify_terminal(
        events=(NotifyEvent(work_item_id="li-1", outcome_class="failed"),),
        run_id="r1",
        poster=poster,
        journal=journal,
        environ={},
    )
    assert poster.calls == []
    assert _stages(journal=journal) == ["notify-skipped"]


def test_notify_terminal_posts_leak_free_body_to_dedicated_topic() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    notify_terminal(
        events=(NotifyEvent(work_item_id="livespec-impl-beads-h1p", outcome_class="failed"),),
        run_id="run-abc",
        poster=poster,
        journal=journal,
        environ={
            "CLAUDE_NTFY_DISPATCHER_TOPIC": "dispatch-alarms",
            "CLAUDE_NTFY_SERVER": "https://n.ex",
        },
    )
    call = poster.calls[0]
    assert call["url"] == "https://n.ex/dispatch-alarms"
    body = call["body"]
    assert isinstance(body, str)
    assert "livespec-impl-beads-h1p" in body
    assert "failed" in body
    assert "run-abc" in body
    assert _stages(journal=journal) == ["notify-sent"]


def test_notify_terminal_records_failed_delivery() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster(result=False)
    notify_terminal(
        events=(NotifyEvent(work_item_id="li-1", outcome_class="blocked"),),
        run_id="r1",
        poster=poster,
        journal=journal,
        environ={"CLAUDE_NTFY_TOPIC": "t"},
    )
    assert _stages(journal=journal) == ["notify-failed"]


def test_notify_terminal_fail_open_when_poster_raises() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster(raises=RuntimeError("network exploded"))
    # Must NOT propagate: the verdict is already final.
    notify_terminal(
        events=(NotifyEvent(work_item_id="li-1", outcome_class="failed"),),
        run_id="r1",
        poster=poster,
        journal=journal,
        environ={"CLAUDE_NTFY_TOPIC": "t"},
    )
    assert _stages(journal=journal) == ["notify-error"]


def test_notify_terminal_body_never_carries_credential_shaped_run_id() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    notify_terminal(
        events=(NotifyEvent(work_item_id="li-1", outcome_class="failed"),),
        run_id="https://x-access-token:ghp_LEAK@github.com/o/r.git",
        poster=poster,
        journal=journal,
        environ={"CLAUDE_NTFY_TOPIC": "t"},
    )
    body = poster.calls[0]["body"]
    assert isinstance(body, str)
    assert "ghp_LEAK" not in body
    assert "[redacted]" in body


def test_notify_terminal_defaults_to_process_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_NTFY_TOPIC", "from-process-env")
    monkeypatch.delenv("CLAUDE_NTFY_DISPATCHER_TOPIC", raising=False)
    monkeypatch.delenv("CLAUDE_NTFY_SERVER", raising=False)
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    notify_terminal(
        events=(NotifyEvent(work_item_id="li-1", outcome_class="failed"),),
        run_id="r1",
        poster=poster,
        journal=journal,
    )
    assert poster.calls[0]["url"] == "https://ntfy.sh/from-process-env"


# --------------------------------------------------------------------------
# HttpNotifyPoster — production seam returns False on error (never raises)
# --------------------------------------------------------------------------


def test_http_notify_poster_returns_false_on_unroutable_url() -> None:
    poster = HttpNotifyPoster()
    # A syntactically valid but unroutable scheme/host: urlopen raises a
    # URLError/OSError, which the poster catches and maps to False — it
    # never raises. A tiny timeout keeps the test fast.
    delivered = poster.post(
        url="http://127.0.0.1:1/dispatch-alarms",
        body="work-item: li-1\noutcome: failed\nrun: r1",
        title="t",
        timeout_seconds=0.01,
    )
    assert delivered is False


def test_http_notify_poster_returns_true_on_2xx(monkeypatch: pytest.MonkeyPatch) -> None:
    """The success path: a delivered POST returns True. `urlopen` is mocked so
    no real network call is made (hang-guard); the production seam's success
    branch is covered without touching ntfy.sh."""
    seen: dict[str, object] = {}

    class _FakeResponse:
        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def _fake_urlopen(request: object, *, timeout: float) -> _FakeResponse:
        seen["request"] = request
        seen["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    poster = HttpNotifyPoster()
    delivered = poster.post(
        url="https://ntfy.sh/dispatch-alarms",
        body="work-item: li-1\noutcome: failed\nrun: r1",
        title="livespec dispatcher: terminal failure",
        timeout_seconds=5.0,
    )
    assert delivered is True
    assert seen["timeout"] == 5.0


# --------------------------------------------------------------------------
# Dispatcher wiring — fail-open at the verdict boundary
# --------------------------------------------------------------------------


def test_alarm_helper_fires_nothing_for_green_wave() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    _alarm_on_terminal_failure(
        outcomes=[_outcome(status="green")],
        include_loop_summary=False,
        journal=journal,
        poster=poster,
    )
    assert poster.calls == []
    assert journal.records == []


def test_alarm_helper_skips_when_topic_unset() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    _alarm_on_terminal_failure(
        outcomes=[_outcome(status="failed")],
        include_loop_summary=False,
        journal=journal,
        poster=poster,
    )
    # Topic scrubbed by the autouse fixture -> the silent no-op path.
    assert poster.calls == []
    assert _stages(journal=journal) == ["notify-skipped"]


def test_dispatch_failed_outcome_journals_notify_and_keeps_exit_code(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed dispatch still exits 1; the alarm rides fail-open after the
    verdict. With a topic set and a recording poster, the leak-free body
    is delivered and journaled — the dispatch `detail` blob never reaches
    it."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "dispatch-alarms")
    poster = _RecordingPoster()
    monkeypatch.setattr(dispatcher, "HttpNotifyPoster", lambda: poster)
    failed = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="host-only-refused",
        pr_number=None,
        merge_sha=None,
        detail="host-route me; token https://x:ghp_LEAK@github.com/o/r.git",
    )
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={item.id: failed}))
    exit_code = dispatcher.main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    _ = capsys.readouterr()
    body = poster.calls[0]["body"]
    assert isinstance(body, str)
    assert item.id in body
    assert "failed" in body
    assert "ghp_LEAK" not in body
    assert "host-route" not in body
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    stages = [json.loads(line)["stage"] for line in journal_text.splitlines()]
    assert "notify-sent" in stages


def test_dispatch_failed_exit_code_unchanged_when_notify_raises(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 0jxs load-bearing invariant: a notify exception NEVER changes the
    verdict. A poster that raises must leave the exit code at 1."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setenv("CLAUDE_NTFY_TOPIC", "general")
    poster = _RecordingPoster(raises=RuntimeError("ntfy down"))
    monkeypatch.setattr(dispatcher, "HttpNotifyPoster", lambda: poster)
    failed = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="boom",
    )
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={item.id: failed}))
    exit_code = dispatcher.main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    _ = capsys.readouterr()
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    stages = [json.loads(line)["stage"] for line in journal_text.splitlines()]
    assert "notify-error" in stages


def test_loop_non_green_wave_alarms_with_loop_summary(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-green loop wave alarms each non-green item AND the non-green-loop
    summary; the verdict stays 1."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "dispatch-alarms")
    poster = _RecordingPoster()
    monkeypatch.setattr(dispatcher, "HttpNotifyPoster", lambda: poster)
    blocked = DispatchOutcome(
        work_item_id=item.id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="parked at human gate",
    )
    monkeypatch.setattr(dispatcher, "run_dispatch", _FakeRunDispatch(outcomes={item.id: blocked}))
    exit_code = dispatcher.main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
        ]
    )
    assert exit_code == 1
    _ = capsys.readouterr()
    bodies = [call["body"] for call in poster.calls]
    joined = "\n".join(b for b in bodies if isinstance(b, str))
    assert "blocked" in joined
    assert "non-green-loop" in joined


def test_loop_all_green_wave_fires_no_alarm(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "dispatch-alarms")
    poster = _RecordingPoster()
    monkeypatch.setattr(dispatcher, "HttpNotifyPoster", lambda: poster)
    monkeypatch.setattr(
        dispatcher,
        "run_dispatch",
        _FakeRunDispatch(outcomes={item.id: _green_outcome(item_id=item.id)}),
    )
    exit_code = dispatcher.main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--mode",
            "autonomous",
            "--workflow",
            str(workflow),
        ]
    )
    assert exit_code == 0
    _ = capsys.readouterr()
    assert poster.calls == []
