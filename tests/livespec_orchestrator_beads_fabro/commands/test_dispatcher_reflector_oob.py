"""Tests for the out-of-band LLM reflector (work-item 29f.4).

Covers `_dispatcher_reflector_oob`: the default-OFF trigger lever, the
`claude -p` + Honeycomb-MCP argv/config wiring (all faked — NO real
`claude -p`, MCP, or PR ever fires in a test, per the self-machinery
hang-guard), structured-findings parsing, the dedup-first ledger filing
lifecycle (file / comment-bump / mute / digest / per-pass cap), the
severity→priority map, the fail-CLOSED scrub on every export, the
`gen_ai.evaluation.result` verdict spans, the lessons-via-PR seam, and the
fail-open + auto-trip discipline. The load-bearing invariant: the reflector
NEVER raises and NEVER touches a verdict — it runs after the verdict is
final, in a daemon thread.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reflector_oob as reflector
from livespec_orchestrator_beads_fabro.commands import (
    _reflector_findings_parse,
    _reflector_lessons,
    _reflector_spans,
)
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflector_oob import (
    _BUDGET_EXCEEDED_MESSAGE,  # pyright: ignore[reportPrivateUsage]
    GitPrLessonsProposer,
    LessonProposal,
    RecordingLessonsProposer,
    ReflectorFinding,
    build_mcp_config,
    claude_reflector_argv,
    fingerprint,
    parse_findings,
    resolve_claude_path,
    resolve_claude_timeout_seconds,
    resolve_mode,
    resolve_reflector_budget_seconds,
    resolve_strict_mcp,
    run_reflector_oob,
    severity_priority,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import REDACTION_MARKER
from livespec_orchestrator_beads_fabro.commands._reflector_filing import (
    check_budget,
    label_index,
    record_labels,
)
from livespec_orchestrator_beads_fabro.commands._reflector_spans import build_span, emit_spans

_MCP_ENV = "HONEYCOMB_MCP_API_KEY_LIVESPEC"
_LEVER_ENV = "LIVESPEC_REFLECTOR_OOB"


@pytest.fixture(autouse=True)
def reset_auto_trip_fixture() -> None:
    reflector.reset_auto_trip()


@pytest.fixture(autouse=True)
def _tmp_repo_connection_config(tmp_path: Path) -> None:
    """Give each test's `tmp_path` repo a `.livespec.jsonc` with a `prefix`.

    The reflector resolves the tenant connection via
    `resolve_store_config(cwd=repo)`, which now REQUIRES an explicit
    `connection.prefix` (decoupled from the tenant DB name). A real governed
    repo always carries one; this fixture mirrors that so the hermetic
    `tmp_path` repos resolve instead of tripping the fail-open guard.
    """
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )


@dataclass(kw_only=True)
class _FakeRunner:
    """Scripted CommandRunner: returns one queued result; logs each call."""

    queue: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        assert timeout_seconds > 0
        _ = cwd
        self.calls.append(argv)
        return self.queue.pop(0) if self.queue else CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _claude_json(findings: list[dict[str, object]]) -> str:
    """The `claude -p --output-format json` envelope carrying the findings."""
    return json.dumps({"result": json.dumps({"findings": findings})})


def _finding(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "category": "stage-timeout",
        "stage": "fabro-run",
        "severity": "critical",
        "subject": "repeated stage timeouts on dispatch",
        "detail": "trace link: https://ui.honeycomb.io/x",
        "occurrences": 4,
        "work_item_id": "li-7",
        "score": 0.2,
        "label": "fail",
    }
    base.update(overrides)
    return base


def _seed_existing(*, repo: Path, fingerprint_hex: str, closed: bool, muted: bool) -> str:
    """Seed an existing fingerprinted issue into the shared fake tenant."""
    config = resolve_store_config(cwd=repo, work_items_arg=None)
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    labels = ["reflection", f"fingerprint:{fingerprint_hex}"]
    if muted:
        labels.append("reflection-mute")
    issue_id = f"{config.prefix}-seeded"
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title="prior reflection item",
            description="prior",
            priority=2,
            assignee=None,
            created_at="2026-06-14T00:00:00Z",
            labels=labels,
        )
    )
    if closed:
        client.close_issue(issue_id=issue_id, reason="done")
    return issue_id


def _arm(monkeypatch: pytest.MonkeyPatch, *, mode: str = "file") -> None:
    monkeypatch.setenv(_LEVER_ENV, mode)
    monkeypatch.setenv(_MCP_ENV, "hcmk-secret-value")


# ---------------------------------------------------------------------------
# Pure helpers.
# ---------------------------------------------------------------------------


def test_resolve_mode_defaults_off() -> None:
    assert resolve_mode(raw=None) == "off"
    assert resolve_mode(raw="") == "off"
    assert resolve_mode(raw="bogus") == "off"
    assert resolve_mode(raw="observe") == "observe"
    assert resolve_mode(raw="file") == "file"


def test_fingerprint_is_stable_message_free_12_hex() -> None:
    a = fingerprint(category="c", stage="s", repo="r", subject="Repeated   Timeout!")
    b = fingerprint(category="c", stage="s", repo="r", subject="repeated timeout!")
    assert a == b  # normalized: lowercased + whitespace-collapsed.
    assert len(a) == 12
    assert all(ch in "0123456789abcdef" for ch in a)
    other = fingerprint(category="c2", stage="s", repo="r", subject="repeated timeout!")
    assert other != a


def test_severity_priority_map() -> None:
    assert severity_priority(severity="critical") == 1
    assert severity_priority(severity="warn") == 2
    assert severity_priority(severity="info") == 4


def test_build_mcp_config_wires_honeycomb_bearer() -> None:
    config = build_mcp_config(api_key="hcmk-xyz")
    # Round-trip through JSON so the assertions read scalars, not `object`.
    rendered = json.loads(json.dumps(config))
    server = rendered["mcpServers"]["honeycomb"]
    assert server["url"] == "https://mcp.honeycomb.io/mcp"
    assert server["headers"]["Authorization"] == "Bearer hcmk-xyz"


def test_reflector_oob_decomposition_modules_export_public_entry_points() -> None:
    assert _reflector_findings_parse.__all__ == ["ReflectorFinding", "parse_findings"]
    assert _reflector_spans.__all__ == [
        "build_span",
        "emit_spans",
        "emit_summary",
        "hex_id",
        "request_line",
    ]
    assert _reflector_lessons.__all__ == [
        "GitPrLessonsProposer",
        "LessonProposal",
        "LessonsProposer",
        "RecordingLessonsProposer",
    ]


def test_claude_reflector_argv_is_headless_with_mcp_config() -> None:
    argv = claude_reflector_argv(
        prompt="review", mcp_config_path=Path("/tmp/mcp.json"), model="claude-x"
    )
    assert argv[:2] == ["claude", "-p"]
    assert "--mcp-config" in argv
    assert "/tmp/mcp.json" in argv
    assert "--model" in argv and "claude-x" in argv


# ---------------------------------------------------------------------------
# 29f.8 gap 1 — time-box resolvers (env-overridable; positive-only).
# ---------------------------------------------------------------------------


def test_claude_timeout_default_is_at_least_600s() -> None:
    # The pre-29f.8 90s ALWAYS timed out (a real review took ~371s); the
    # default is raised well above that so the judge can actually finish.
    assert resolve_claude_timeout_seconds(environ={}) >= 600.0


def test_claude_timeout_env_override_and_bad_value_fallback() -> None:
    assert (
        resolve_claude_timeout_seconds(environ={"LIVESPEC_REFLECTOR_CLAUDE_TIMEOUT_SECONDS": "900"})
        == 900.0
    )
    # Unparseable / non-positive values fall back to the committed default.
    default = resolve_claude_timeout_seconds(environ={})
    assert (
        resolve_claude_timeout_seconds(
            environ={"LIVESPEC_REFLECTOR_CLAUDE_TIMEOUT_SECONDS": "not-a-number"}
        )
        == default
    )
    assert (
        resolve_claude_timeout_seconds(environ={"LIVESPEC_REFLECTOR_CLAUDE_TIMEOUT_SECONDS": "0"})
        == default
    )


def test_reflector_budget_sits_above_the_claude_timeout() -> None:
    # The stage budget must exceed the claude subprocess ceiling so the
    # subprocess timeout (not _check_budget) is the tripwire on a hung judge.
    assert resolve_reflector_budget_seconds(environ={}) > resolve_claude_timeout_seconds(environ={})


def test_reflector_budget_env_override_and_bad_value_fallback() -> None:
    assert (
        resolve_reflector_budget_seconds(environ={"LIVESPEC_REFLECTOR_BUDGET_SECONDS": "1200"})
        == 1200.0
    )
    default = resolve_reflector_budget_seconds(environ={})
    assert (
        resolve_reflector_budget_seconds(environ={"LIVESPEC_REFLECTOR_BUDGET_SECONDS": "garbage"})
        == default
    )


# ---------------------------------------------------------------------------
# 29f.8 gap 3 — `claude` PATH resolution under the minimal env-wrapper PATH.
# ---------------------------------------------------------------------------


def test_resolve_claude_path_prefers_explicit_override() -> None:
    assert (
        resolve_claude_path(environ={"LIVESPEC_REFLECTOR_CLAUDE_PATH": "/opt/claude/bin/claude"})
        == "/opt/claude/bin/claude"
    )


def test_resolve_claude_path_uses_which_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reflector.shutil, "which", lambda _name: "/usr/bin/claude")
    assert resolve_claude_path(environ={}) == "/usr/bin/claude"


def test_resolve_claude_path_falls_back_to_local_bin_then_bare(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(reflector.shutil, "which", lambda _name: None)
    # local-bin fallback exists → that path is used.
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    fake_claude = local_bin / "claude"
    _ = fake_claude.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(reflector, "_CLAUDE_LOCAL_BIN_FALLBACK", str(fake_claude))
    assert resolve_claude_path(environ={}) == str(fake_claude)
    # nothing on PATH and no local-bin file → bare "claude" (lets the runner
    # surface the FileNotFoundError honestly rather than guessing).
    monkeypatch.setattr(reflector, "_CLAUDE_LOCAL_BIN_FALLBACK", str(tmp_path / "nope" / "claude"))
    assert resolve_claude_path(environ={}) == "claude"


# ---------------------------------------------------------------------------
# 29f.8 gap 4 — headless MCP tool permission scoped to the honeycomb server.
# ---------------------------------------------------------------------------


def test_claude_reflector_argv_allows_only_the_honeycomb_mcp_server() -> None:
    argv = claude_reflector_argv(
        prompt="review",
        mcp_config_path=Path("/tmp/mcp.json"),
        model="claude-x",
        claude_path="/abs/claude",
    )
    assert "--allowedTools" in argv
    scope = argv[argv.index("--allowedTools") + 1]
    # Scoped to the configured "honeycomb" MCP server only — the minimal grant.
    assert scope == "mcp__honeycomb"
    # NEVER the blanket skip-permissions escape hatch.
    assert "--dangerously-skip-permissions" not in argv
    # The resolved claude path is argv[0] (29f.8 gap 3 threaded through).
    assert argv[0] == "/abs/claude"


# ---------------------------------------------------------------------------
# 29f.8 follow-up — strict-MCP isolation (durable hosted-key path only).
#
# Without `--strict-mcp-config` the headless judge can pick up an ambient
# OAuth honeycomb plugin whose token expires unattended; strict-by-default
# pins the judge to ONLY the `--mcp-config` hosted server (the durable
# API-key path). The lever is the explicit opt-out escape hatch.
# ---------------------------------------------------------------------------


def test_resolve_strict_mcp_defaults_on_when_unset() -> None:
    # Unset → strict ON, so the judge never falls back to an ambient plugin.
    assert resolve_strict_mcp(environ={}) is True


def test_resolve_strict_mcp_stays_on_for_truthy_and_unknown_values() -> None:
    # Any non-falsey value (incl. an explicit truthy one) keeps strict ON.
    assert resolve_strict_mcp(environ={"LIVESPEC_REFLECTOR_STRICT_MCP": "on"}) is True
    assert resolve_strict_mcp(environ={"LIVESPEC_REFLECTOR_STRICT_MCP": "1"}) is True
    assert resolve_strict_mcp(environ={"LIVESPEC_REFLECTOR_STRICT_MCP": "true"}) is True
    assert resolve_strict_mcp(environ={"LIVESPEC_REFLECTOR_STRICT_MCP": "whatever"}) is True


def test_resolve_strict_mcp_explicit_falsey_disables_case_insensitively() -> None:
    # Explicit falsey values are the opt-out escape hatch; case/whitespace tolerant.
    for falsey in ("off", "OFF", "false", "False", "0", "no", "  off  "):
        assert resolve_strict_mcp(environ={"LIVESPEC_REFLECTOR_STRICT_MCP": falsey}) is False


def test_claude_reflector_argv_appends_strict_mcp_config_by_default() -> None:
    # Default (strict_mcp omitted) pins the judge to ONLY the --mcp-config server.
    argv = claude_reflector_argv(
        prompt="review",
        mcp_config_path=Path("/tmp/mcp.json"),
        model="claude-x",
        claude_path="/abs/claude",
    )
    assert "--strict-mcp-config" in argv


def test_claude_reflector_argv_omits_strict_mcp_config_when_opted_out() -> None:
    # strict_mcp=False reproduces the pre-follow-up behavior (ambient plugins allowed).
    argv = claude_reflector_argv(
        prompt="review",
        mcp_config_path=Path("/tmp/mcp.json"),
        model="claude-x",
        claude_path="/abs/claude",
        strict_mcp=False,
    )
    assert "--strict-mcp-config" not in argv
    # The honeycomb --mcp-config wiring is unaffected by the opt-out.
    assert "--mcp-config" in argv
    assert argv[argv.index("--allowedTools") + 1] == "mcp__honeycomb"


def test_parse_findings_accepts_claude_json_envelope() -> None:
    findings = parse_findings(raw=_claude_json([_finding()]))
    assert len(findings) == 1
    assert findings[0].category == "stage-timeout"
    assert findings[0].occurrences == 4


def test_parse_findings_accepts_bare_array_and_findings_envelope() -> None:
    assert len(parse_findings(raw=json.dumps([_finding()]))) == 1
    assert len(parse_findings(raw=json.dumps({"findings": [_finding()]}))) == 1


def test_parse_findings_skips_malformed_and_unparseable_failsoft() -> None:
    raw = json.dumps({"findings": [_finding(), {"no": "required-keys"}, 42]})
    assert len(parse_findings(raw=raw)) == 1
    assert parse_findings(raw="not json at all") == ()
    assert parse_findings(raw="") == ()


# ---------------------------------------------------------------------------
# Trigger / fail-open / off paths.
# ---------------------------------------------------------------------------


def test_off_by_default_runs_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_LEVER_ENV, raising=False)
    runner = _FakeRunner(queue=[])
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    assert runner.calls == []  # NO claude -p when the lever is off.
    assert journal.records == []


def test_armed_but_no_mcp_key_skips_without_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_LEVER_ENV, "file")
    monkeypatch.delenv(_MCP_ENV, raising=False)
    runner = _FakeRunner(queue=[])
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    assert runner.calls == []
    assert journal.records[-1]["stage"] == "reflector-oob-skipped"


def test_observe_mode_runs_claude_emits_spans_files_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _arm(monkeypatch, mode="observe")
    runner = _FakeRunner(
        queue=[CommandResult(exit_code=0, stdout=_claude_json([_finding()]), stderr="")]
    )
    journal = _RecordingJournal()
    spans_path = tmp_path / "spans.jsonl"
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=spans_path,
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    # claude -p ran once; spans were written; NO ledger item was filed.
    # argv[0] is the RESOLVED claude path (29f.8 gap 3 — may be absolute under
    # the env wrapper), so match on the basename + the headless `-p` flag.
    assert any(Path(call[0]).name == "claude" and call[1] == "-p" for call in runner.calls)
    assert spans_path.is_file()
    stages = [rec.get("stage") for rec in journal.records]
    assert "reflector-oob" in stages
    assert "reflector-oob-filed" not in stages
    err = capsys.readouterr().err
    assert "reflector-oob (observe)" in err


def test_reflector_never_raises_on_runner_explosion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch)

    @dataclass(kw_only=True)
    class _Boom:
        def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
            _ = (argv, cwd, timeout_seconds)
            raise RuntimeError("claude exploded")

    journal = _RecordingJournal()
    # Must NOT raise: the daemon-thread body is fail-open.
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=_Boom(),
        lessons_proposer=RecordingLessonsProposer(),
    )
    assert journal.records[-1]["stage"] == "reflector-oob-error"


def test_auto_trip_disables_after_three_consecutive_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch)

    @dataclass(kw_only=True)
    class _Boom:
        def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
            _ = (argv, cwd, timeout_seconds)
            raise RuntimeError("boom")

    journal = _RecordingJournal()
    for _ in range(3):
        run_reflector_oob(
            repo=tmp_path,
            journal=journal,
            spans_path=tmp_path / "spans.jsonl",
            runner=_Boom(),
            lessons_proposer=RecordingLessonsProposer(),
        )
    stages = [rec.get("stage") for rec in journal.records]
    assert "reflector-oob-tripped" in stages


# ---------------------------------------------------------------------------
# Dedup-first filing lifecycle.
# ---------------------------------------------------------------------------


def test_file_mode_files_a_new_critical_item_with_dedup_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch)
    runner = _FakeRunner(
        queue=[CommandResult(exit_code=0, stdout=_claude_json([_finding()]), stderr="")]
    )
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    client = make_beads_client(config=config)
    items = client.list_issues()
    filed = [i for i in items if "reflection" in i.get("labels", [])]
    assert len(filed) == 1
    labels = filed[0]["labels"]
    assert any(label.startswith("fingerprint:") for label in labels)
    assert filed[0]["priority"] == 1  # critical → P1
    assert filed[0]["issue_type"] == "bug"


def test_file_mode_bumps_existing_open_item_instead_of_refiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch)
    fp = fingerprint(
        category="stage-timeout",
        stage="fabro-run",
        repo=str(tmp_path),
        subject="repeated stage timeouts on dispatch",
    )
    existing = _seed_existing(repo=tmp_path, fingerprint_hex=fp, closed=False, muted=False)
    runner = _FakeRunner(
        queue=[CommandResult(exit_code=0, stdout=_claude_json([_finding()]), stderr="")]
    )
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    # No NEW reflection item filed; the existing one got a comment-bump.
    reflection_items = [i for i in client.list_issues() if "reflection" in i.get("labels", [])]
    assert len(reflection_items) == 1
    comments = client.list_comments(issue_id=existing)
    assert len(comments) == 1
    assert "recurrence" in comments[0]["text"]


def test_file_mode_never_refiles_a_muted_closed_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch)
    fp = fingerprint(
        category="stage-timeout",
        stage="fabro-run",
        repo=str(tmp_path),
        subject="repeated stage timeouts on dispatch",
    )
    _ = _seed_existing(repo=tmp_path, fingerprint_hex=fp, closed=True, muted=True)
    runner = _FakeRunner(
        queue=[CommandResult(exit_code=0, stdout=_claude_json([_finding()]), stderr="")]
    )
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    client = make_beads_client(config=config)
    # Only the seeded (muted, closed) item exists — nothing re-filed.
    reflection_items = [i for i in client.list_issues() if "reflection" in i.get("labels", [])]
    assert len(reflection_items) == 1
    oob = next(r for r in journal.records if r.get("stage") == "reflector-oob")
    assert oob["muted"]


def test_info_severity_is_digest_only_no_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch)
    runner = _FakeRunner(
        queue=[
            CommandResult(exit_code=0, stdout=_claude_json([_finding(severity="info")]), stderr="")
        ]
    )
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    client = make_beads_client(config=config)
    filed = [i for i in client.list_issues() if "reflection" in i.get("labels", [])]
    assert filed == []


def test_warn_severity_files_only_at_two_or_more_occurrences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch)
    runner = _FakeRunner(
        queue=[
            CommandResult(
                exit_code=0,
                stdout=_claude_json(
                    [
                        _finding(severity="warn", occurrences=1, category="warn-single"),
                        _finding(severity="warn", occurrences=2, category="warn-recurring"),
                    ]
                ),
                stderr="",
            )
        ]
    )
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    client = make_beads_client(config=config)
    titles = [i["title"] for i in client.list_issues() if "reflection" in i.get("labels", [])]
    assert any("warn-recurring" in t for t in titles)
    assert not any("warn-single" in t for t in titles)


def test_caps_new_items_at_three_per_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _arm(monkeypatch)
    many = [_finding(category=f"crit-{i}", subject=f"distinct subject {i}") for i in range(5)]
    runner = _FakeRunner(queue=[CommandResult(exit_code=0, stdout=_claude_json(many), stderr="")])
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    client = make_beads_client(config=config)
    filed = [i for i in client.list_issues() if "reflection" in i.get("labels", [])]
    assert len(filed) == 3  # capped, even though 5 critical findings arrived.


# ---------------------------------------------------------------------------
# Scrub on export.
# ---------------------------------------------------------------------------


def test_filed_body_is_scrubbed_failclosed_on_credential_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch)
    leak = "see https://x-access-token:ghp_SECRETVALUE@github.com/o/r for the trace"
    runner = _FakeRunner(
        queue=[CommandResult(exit_code=0, stdout=_claude_json([_finding(detail=leak)]), stderr="")]
    )
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    client = make_beads_client(config=config)
    filed = [i for i in client.list_issues() if "reflection" in i.get("labels", [])]
    assert filed[0]["description"] == REDACTION_MARKER
    assert "ghp_SECRETVALUE" not in filed[0]["description"]


# ---------------------------------------------------------------------------
# Verdict spans.
# ---------------------------------------------------------------------------


def test_verdict_spans_are_gen_ai_evaluation_result_parented_to_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch, mode="observe")
    runner = _FakeRunner(
        queue=[CommandResult(exit_code=0, stdout=_claude_json([_finding()]), stderr="")]
    )
    journal = _RecordingJournal()
    spans_path = tmp_path / "spans.jsonl"
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=spans_path,
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    line = spans_path.read_text(encoding="utf-8").splitlines()[0]
    request = json.loads(line)
    spans = request["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert spans[0]["name"] == "gen_ai.evaluation.result"
    # A correlated finding (work_item_id present) parents the verdict span.
    assert "parentSpanId" in spans[0]
    attr_keys = {a["key"] for a in spans[0]["attributes"]}
    assert "gen_ai.evaluation.name" in attr_keys
    assert "work.item.id" in attr_keys


# ---------------------------------------------------------------------------
# Lessons-via-PR seam.
# ---------------------------------------------------------------------------


def test_critical_finding_proposes_a_lesson_via_the_pr_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch)
    proposer = RecordingLessonsProposer()
    runner = _FakeRunner(
        queue=[CommandResult(exit_code=0, stdout=_claude_json([_finding()]), stderr="")]
    )
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=proposer,
    )
    assert len(proposer.proposals) == 1
    assert isinstance(proposer.proposals[0], LessonProposal)
    stages = [rec.get("stage") for rec in journal.records]
    assert "reflector-oob-lesson-proposed" in stages


def test_no_critical_finding_proposes_no_lesson(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm(monkeypatch)
    proposer = RecordingLessonsProposer()
    runner = _FakeRunner(
        queue=[
            CommandResult(exit_code=0, stdout=_claude_json([_finding(severity="info")]), stderr="")
        ]
    )
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=proposer,
    )
    assert proposer.proposals == []


def test_recording_lessons_proposer_records_without_side_effects(tmp_path: Path) -> None:
    proposer = RecordingLessonsProposer()
    ref = proposer.propose(proposal=LessonProposal(title="t", body="b"), repo=tmp_path)
    assert ref == "https://example.invalid/pr/0"
    assert proposer.proposals[0].title == "t"


def test_reflector_finding_dataclass_is_frozen() -> None:
    finding = ReflectorFinding(
        category="c",
        stage="s",
        severity="warn",
        subject="x",
        detail="d",
        occurrences=2,
        work_item_id=None,
        score=0.5,
        label="pass",
    )
    with pytest.raises(AttributeError):
        finding.category = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Defensive-branch coverage (fail-soft parsing / indexing / span / budget).
# ---------------------------------------------------------------------------


def test_parse_findings_skips_finding_missing_required_keys() -> None:
    # `occurrences`/`score` non-numeric defaults are taken; a finding missing
    # `category`/`severity`/`subject` is dropped (fail-soft).
    raw = json.dumps(
        {
            "findings": [
                {
                    "category": "c",
                    "severity": "warn",
                    "subject": "s",
                    "occurrences": "not-an-int",
                    "score": "not-a-float",
                },
                {"severity": "warn"},
            ]
        }
    )
    findings = parse_findings(raw=raw)
    assert len(findings) == 1
    assert findings[0].occurrences == 1  # default
    assert findings[0].score == 0.0  # default


def test_parse_findings_unknown_payload_shapes_yield_empty() -> None:
    assert parse_findings(raw=json.dumps({"other": 1})) == ()
    assert parse_findings(raw=json.dumps({"result": 99})) == ()
    assert parse_findings(raw=json.dumps(42)) == ()


def test_parse_findings_bool_numeric_fields_fall_back_to_defaults() -> None:
    raw = json.dumps(
        {
            "findings": [
                {
                    "category": "c",
                    "severity": "warn",
                    "subject": "s",
                    "occurrences": True,
                    "score": False,
                }
            ]
        }
    )
    findings = parse_findings(raw=raw)
    assert findings[0].occurrences == 1
    assert findings[0].score == 0.0


def test_label_index_skips_records_without_fingerprint_or_with_bad_shapes() -> None:
    fake = FakeBeadsClient()
    # A record with NO fingerprint label (skipped at the `continue`).
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id="li-plain",
            issue_type="task",
            title="plain",
            description="d",
            priority=2,
            assignee=None,
            created_at="2026-06-14T00:00:00Z",
            labels=["unrelated"],
        )
    )
    # A record WITH a fingerprint label is indexed.
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id="li-fp",
            issue_type="task",
            title="fp",
            description="d",
            priority=2,
            assignee=None,
            created_at="2026-06-14T00:00:00Z",
            labels=["reflection", "fingerprint:abc123abc123"],
        )
    )
    index = label_index(client=fake)
    assert "abc123abc123" in index
    assert index["abc123abc123"].issue_id == "li-fp"
    assert len(index) == 1  # the plain record was skipped.


def test_record_labels_failsoft_on_non_list_labels() -> None:
    assert record_labels(record={"labels": "not-a-list"}) == []
    assert record_labels(record={}) == []
    assert record_labels(record={"labels": ["a", 1, "b"]}) == ["a", "b"]


def test_label_index_skips_records_with_non_string_id() -> None:
    @dataclass(kw_only=True)
    class _MalformedClient:
        """Minimal client returning records the FakeBeadsClient can't mint."""

        def list_issues(self) -> list[dict[str, object]]:
            return [
                # Fingerprint label present but a non-str id → skipped (862).
                {"id": 123, "labels": ["fingerprint:deadbeefcafe"], "status": "open"},
                # Non-list labels → _record_labels returns [] (870), no fp → skip.
                {"id": "li-bad-labels", "labels": "not-a-list", "status": "open"},
            ]

    index = label_index(client=_MalformedClient())  # type: ignore[arg-type]
    assert index == {}


def test_emit_spans_no_findings_writes_nothing(tmp_path: Path) -> None:
    spans_path = tmp_path / "spans.jsonl"
    emit_spans(findings=(), spans_path=spans_path)
    assert not spans_path.exists()


def test_emit_spans_uncorrelated_finding_is_a_root_verdict_span(tmp_path: Path) -> None:
    finding = ReflectorFinding(
        category="c",
        stage="s",
        severity="warn",
        subject="x",
        detail="d",
        occurrences=1,
        work_item_id=None,  # uncorrelated → root span, no parent.
        score=0.9,
        label="pass",
    )
    spans_path = tmp_path / "spans.jsonl"
    emit_spans(findings=(finding,), spans_path=spans_path)
    request = json.loads(spans_path.read_text(encoding="utf-8").splitlines()[0])
    span = request["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert "parentSpanId" not in span
    attr_keys = {a["key"] for a in span["attributes"]}
    assert "work.item.id" not in attr_keys


def test_build_span_without_parent_omits_parent_span_id() -> None:
    span = build_span(
        name="n",
        span_id="s",
        attrs={"k": 1},
        parent_id=None,
        start_ns=1,
        end_ns=2,
    )
    assert "parentSpanId" not in span


def test_check_budget_raises_when_deadline_passed() -> None:
    with pytest.raises(TimeoutError, match=_BUDGET_EXCEEDED_MESSAGE):
        check_budget(deadline=0.0)  # a deadline in the deep past trips it.


def test_run_pass_aborts_when_budget_exceeded_midpass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A zero-second budget makes the post-claude `_check_budget` trip; the
    # fail-open supervisor catches it and journals a reflector-oob-error.
    _arm(monkeypatch)
    monkeypatch.setattr(reflector, "_REFLECTOR_BUDGET_SECONDS", 0.0)
    runner = _FakeRunner(
        queue=[CommandResult(exit_code=0, stdout=_claude_json([_finding()]), stderr="")]
    )
    journal = _RecordingJournal()
    run_reflector_oob(
        repo=tmp_path,
        journal=journal,
        spans_path=tmp_path / "spans.jsonl",
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
    )
    reasons = [
        rec.get("reason") for rec in journal.records if rec.get("stage") == "reflector-oob-error"
    ]
    assert any(_BUDGET_EXCEEDED_MESSAGE in str(r) for r in reasons)


def test_git_pr_lessons_proposer_defaults_to_top_level_lessons_path() -> None:
    # The lessons digest lives at the TOP-LEVEL loop-reflection-gate/ home
    # (moved out of research/, livespec-gt7crt); construction crosses no
    # runner seam, so no queued results are needed.
    proposer = GitPrLessonsProposer(runner=_FakeRunner(queue=[]))
    assert proposer.lessons_path == Path("loop-reflection-gate/lessons.md")
