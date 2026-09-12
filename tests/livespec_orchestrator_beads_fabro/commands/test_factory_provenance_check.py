"""Tests for the factory-provenance merge gate (R6a of mechanically-enforce-factory-usage)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._factory_bypass_product_paths import (
    FLEET_FALLBACK_PRODUCT_PREFIXES,
    ProductPathPolicy,
)
from livespec_orchestrator_beads_fabro.commands._factory_provenance_event import PullRequestEvent
from livespec_orchestrator_beads_fabro.commands.factory_provenance_check import (
    FACTORY_APP_LOGINS,
    FACTORY_OVERRIDE_LABEL,
    decide,
    exit_code,
    main,
    permits_merge,
    render_verdict,
    resolve_product_policy,
)

_PRODUCT_PY = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/thing.py"
_TEST_PY = "tests/livespec_orchestrator_beads_fabro/commands/test_thing.py"
_SPEC_MD = "SPECIFICATION/contracts.md"
_POLICY = ProductPathPolicy(prefixes=(".claude-plugin/scripts/",), origin="declared")


class StubRunner:
    """A CommandRunner answering every argv with one canned result."""

    def __init__(self, *, result: CommandResult) -> None:
        self.result = result

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del argv, cwd, timeout_seconds, env, stdin
        return self.result


def _event(*, login: str = "thewoolleyman", labels: tuple[str, ...] = ()) -> PullRequestEvent:
    return PullRequestEvent(
        author_login=login,
        labels=labels,
        base_sha="base1234",
        head_sha="head5678",
    )


def _write_event(*, path: Path, login: str, labels: tuple[str, ...] = ()) -> None:
    _ = path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "user": {"login": login},
                    "labels": [{"name": name} for name in labels],
                    "base": {"sha": "base1234"},
                    "head": {"sha": "head5678"},
                }
            }
        ),
        encoding="utf-8",
    )


def _repo_with_declaration(*, root: Path) -> Path:
    _ = (root / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = [".claude-plugin/scripts"]\n',
        encoding="utf-8",
    )
    return root


def test_a_non_factory_author_changing_product_python_without_the_label_fails() -> None:
    verdict = decide(event=_event(), changed_paths=(_PRODUCT_PY,), policy=_POLICY)
    assert verdict.outcome == "fail"
    assert verdict.product_paths == (_PRODUCT_PY,)
    assert permits_merge(verdict=verdict) is False
    assert exit_code(verdict=verdict) == 1


@pytest.mark.parametrize("login", FACTORY_APP_LOGINS)
def test_both_factory_app_login_spellings_pass(login: str) -> None:
    verdict = decide(event=_event(login=login), changed_paths=(_PRODUCT_PY,), policy=_POLICY)
    assert verdict.outcome == "pass"
    assert verdict.factory_authored is True
    assert permits_merge(verdict=verdict) is True
    assert exit_code(verdict=verdict) == 0


def test_the_factory_override_label_passes_a_non_factory_author() -> None:
    verdict = decide(
        event=_event(labels=(FACTORY_OVERRIDE_LABEL,)),
        changed_paths=(_PRODUCT_PY,),
        policy=_POLICY,
    )
    assert verdict.outcome == "pass"
    assert verdict.override_labeled is True
    assert permits_merge(verdict=verdict) is True


def test_a_diff_touching_no_product_python_permits_the_merge() -> None:
    verdict = decide(event=_event(), changed_paths=(_SPEC_MD, _TEST_PY), policy=_POLICY)
    assert verdict.product_paths == ()
    assert verdict.judged_path_count == 2
    assert permits_merge(verdict=verdict) is True
    assert exit_code(verdict=verdict) == 0
    # Ratified scoped-check vacuity clause: a scope that matched zero files
    # observed nothing, so the EVIDENCE it reports is vacuity rather than a
    # pass. The merge is permitted either way — that is what the two
    # assertions above establish.
    assert verdict.outcome == "vacuous-match"


def test_the_failure_message_names_the_author_and_the_product_paths() -> None:
    verdict = decide(event=_event(), changed_paths=(_PRODUCT_PY, _SPEC_MD), policy=_POLICY)
    message = render_verdict(verdict=verdict)
    assert "@thewoolleyman" in message
    assert _PRODUCT_PY in message
    assert _SPEC_MD not in message
    assert FACTORY_APP_LOGINS[0] in message
    assert f"`{FACTORY_OVERRIDE_LABEL}` label" in message
    assert "pull request body" in message


def test_the_pass_message_names_which_ground_admitted_the_change() -> None:
    app_verdict = decide(
        event=_event(login=FACTORY_APP_LOGINS[0]), changed_paths=(_PRODUCT_PY,), policy=_POLICY
    )
    override_verdict = decide(
        event=_event(labels=(FACTORY_OVERRIDE_LABEL,)),
        changed_paths=(_PRODUCT_PY,),
        policy=_POLICY,
    )
    assert "factory GitHub App" in render_verdict(verdict=app_verdict)
    assert FACTORY_OVERRIDE_LABEL in render_verdict(verdict=override_verdict)


def test_the_vacuous_message_says_it_observed_nothing_and_does_not_block() -> None:
    verdict = decide(event=_event(), changed_paths=(_SPEC_MD,), policy=_POLICY)
    message = render_verdict(verdict=verdict)
    assert "vacuous-match" in message
    assert "not a pass" in message
    assert "not blocked" in message


def test_resolve_product_policy_reads_the_repository_declaration(tmp_path: Path) -> None:
    policy = resolve_product_policy(repo=_repo_with_declaration(root=tmp_path))
    assert policy.origin == "declared"
    assert policy.prefixes == (".claude-plugin/scripts/",)


def test_resolve_product_policy_falls_back_when_the_repository_declares_nothing(
    tmp_path: Path,
) -> None:
    policy = resolve_product_policy(repo=tmp_path)
    assert policy.origin == "fleet-fallback"
    assert policy.prefixes == FLEET_FALLBACK_PRODUCT_PREFIXES


def test_main_fails_a_hand_authored_product_python_pull_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman")
    code = main(
        argv=[
            "--event-path",
            str(event_path),
            "--repo",
            str(repo),
            "--changed-file",
            _PRODUCT_PY,
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "may not merge" in captured.err
    assert _PRODUCT_PY in captured.err
    assert captured.out == ""


def test_main_passes_a_factory_authored_pull_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman-factory-bot[bot]")
    code = main(
        argv=[
            "--event-path",
            str(event_path),
            "--repo",
            str(repo),
            "--changed-file",
            _PRODUCT_PY,
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "pass" in captured.out
    assert captured.err == ""


def test_main_reads_the_changed_paths_from_git_when_no_changed_file_is_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman")
    code = main(
        argv=["--event-path", str(event_path), "--repo", str(repo)],
        runner=StubRunner(result=CommandResult(exit_code=0, stdout=f"{_PRODUCT_PY}\n", stderr="")),
    )
    assert code == 1
    assert _PRODUCT_PY in capsys.readouterr().err


def test_main_takes_the_event_path_from_the_actions_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman", labels=(FACTORY_OVERRIDE_LABEL,))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    code = main(argv=["--repo", str(repo), "--changed-file", _PRODUCT_PY])
    assert code == 0
    assert FACTORY_OVERRIDE_LABEL in capsys.readouterr().out


def test_main_refuses_when_no_event_payload_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    code = main(argv=[])
    assert code == 2
    assert "no event payload" in capsys.readouterr().err


def test_main_refuses_an_unreadable_event_payload_rather_than_passing_unobserved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "absent.json"
    code = main(argv=["--event-path", str(missing)])
    captured = capsys.readouterr()
    assert code == 2
    assert "could not read a pull_request event payload" in captured.err
    assert str(missing) in captured.err


def test_main_refuses_when_the_diff_cannot_be_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_declaration(root=tmp_path)
    event_path = tmp_path / "event.json"
    _write_event(path=event_path, login="thewoolleyman")
    code = main(
        argv=["--event-path", str(event_path), "--repo", str(repo)],
        runner=StubRunner(result=CommandResult(exit_code=128, stdout="", stderr="bad revision")),
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "base1234...head5678" in captured.err
    assert "fetch-depth: 0" in captured.err
