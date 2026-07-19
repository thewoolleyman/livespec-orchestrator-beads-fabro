"""Coverage for the livespec footgun guard — a Claude Code PreToolUse (Bash) hook.

The guard's whole contract is the distinction between a footgun that is EXECUTED
and one that merely appears as DATA. `git commit --no-verify` as the leading
command of a shell segment is blocked; the identical bytes inside an `echo`
argument, a here-doc body, or a non-git command are not. These tests read as the
documentation of that line.

`.claude/hooks/` is not an importable package, so the module is loaded by file
location — the same idiom `test_fleet_pat_dispatch_surface_helpers.py` uses.
Every test is PURE: nothing spawns the hook as a subprocess
(`check-tests-no-subprocess-spawn`); `main()` is driven in-process with a
`StringIO` standing in for `sys.stdin`.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_PATH = _REPO_ROOT / ".claude" / "hooks" / "livespec_footgun_guard.py"
_MODULE_NAME = "livespec_footgun_guard_under_test"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


guard = _load_hook()

# The guard's helpers are module-private by design; the tests exercise them
# directly, so alias them once here rather than sprinkling `noqa` at each call.
strip_heredoc_bodies = guard._strip_heredoc_bodies  # noqa: SLF001
segments = guard._segments  # noqa: SLF001
strip_leading_noise = guard._strip_leading_noise  # noqa: SLF001
git_subcommand = guard._git_subcommand  # noqa: SLF001
check_segment = guard._check_segment  # noqa: SLF001


def _bash_payload(*, command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def _drive_main(*, payload: str | Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run `main()` in-process over `payload` and assert it always exits 0."""
    stdin = io.StringIO(payload) if isinstance(payload, str) else payload
    monkeypatch.setattr(sys, "stdin", stdin)
    with pytest.raises(SystemExit) as exit_info:
        guard.main()
    assert exit_info.value.code == 0


class _ExplodingStdin:
    """A `sys.stdin` stand-in whose `read()` raises a non-JSON error."""

    def read(self) -> str:
        raise RuntimeError("stdin went away")


# ---------------------------------------------------------------------------
# _strip_heredoc_bodies — here-doc bodies are file DATA, never commands
# ---------------------------------------------------------------------------


def test_heredoc_body_is_dropped_and_the_introducing_line_is_kept() -> None:
    command = "cat > f <<'EOF'\ngit commit --no-verify\nEOF\ngit status"

    assert strip_heredoc_bodies(command=command) == "cat > f <<'EOF'\ngit status"


def test_heredoc_body_running_to_end_of_input_drops_everything_after_it() -> None:
    # No terminator line ever arrives, so the scan hits EOF with nothing left
    # to skip past.
    command = "cat <<EOF\ngit commit --no-verify"

    assert strip_heredoc_bodies(command=command) == "cat <<EOF"


def test_indented_heredoc_form_terminates_on_a_tab_indented_terminator() -> None:
    command = "cat <<-EOF\n\tgit push --no-verify\n\tEOF\ngit log"

    assert strip_heredoc_bodies(command=command) == "cat <<-EOF\ngit log"


def test_command_without_a_heredoc_is_returned_unchanged() -> None:
    command = "git status\ngit log --oneline"

    assert strip_heredoc_bodies(command=command) == command


def test_a_heredoc_body_carrying_a_footgun_does_not_block(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _bash_payload(command="cat > note.txt <<'EOF'\ngit commit --no-verify\nEOF")

    _drive_main(payload=payload, monkeypatch=monkeypatch)

    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# _segments — split on &&, ||, ;, |, newline; empty segments are discarded
# ---------------------------------------------------------------------------


def test_segments_splits_on_every_shell_operator_and_drops_empty_pieces() -> None:
    command = "; git status && git log | grep x ;; echo done\n"

    assert segments(command=command) == ["git status", "git log", "grep x", "echo done"]


# ---------------------------------------------------------------------------
# _strip_leading_noise — peel env-assignments and sudo/env/mise wrappers
# ---------------------------------------------------------------------------


def test_a_bare_command_has_no_leading_noise_to_strip() -> None:
    assert strip_leading_noise(tokens=["git", "status"]) == (["git", "status"], False)


def test_leading_env_assignments_are_peeled_off_the_command() -> None:
    tokens = ["FOO=1", "BAR=baz", "git", "status"]

    assert strip_leading_noise(tokens=tokens) == (["git", "status"], False)


def test_a_command_that_is_only_env_assignments_leaves_no_command_behind() -> None:
    assert strip_leading_noise(tokens=["FOO=1"]) == ([], False)


@pytest.mark.parametrize(
    "assignment", ["LEFTHOOK=0", "LEFTHOOK=false", "lefthook=OFF", "LeftHook=no"]
)
def test_a_lefthook_disabling_assignment_is_detected_case_insensitively(assignment: str) -> None:
    _, lefthook_off = strip_leading_noise(tokens=[assignment, "git", "commit"])

    assert lefthook_off is True


def test_a_lefthook_assignment_that_does_not_disable_it_is_not_flagged() -> None:
    _, lefthook_off = strip_leading_noise(tokens=["LEFTHOOK=1", "git", "commit"])

    assert lefthook_off is False


def test_a_sudo_wrapper_and_the_env_assignments_after_it_are_peeled() -> None:
    tokens = ["sudo", "FOO=1", "git", "push"]

    assert strip_leading_noise(tokens=tokens) == (["git", "push"], False)


def test_an_env_wrapper_with_nothing_after_its_assignments_leaves_no_command() -> None:
    assert strip_leading_noise(tokens=["env", "FOO=1"]) == ([], False)


def test_a_wrapper_with_no_following_tokens_leaves_no_command() -> None:
    assert strip_leading_noise(tokens=["sudo"]) == ([], False)


def test_mise_exec_with_a_double_dash_terminator_is_peeled() -> None:
    tokens = ["mise", "exec", "--", "git", "commit"]

    assert strip_leading_noise(tokens=tokens) == (["git", "commit"], False)


def test_mise_exec_without_a_double_dash_terminator_is_peeled() -> None:
    tokens = ["mise", "exec", "git", "commit"]

    assert strip_leading_noise(tokens=tokens) == (["git", "commit"], False)


def test_the_mise_x_alias_is_peeled() -> None:
    assert strip_leading_noise(tokens=["mise", "x", "git", "status"]) == (["git", "status"], False)


def test_mise_flags_before_exec_are_peeled_along_with_the_wrapper() -> None:
    tokens = ["mise", "-y", "exec", "--", "git", "push"]

    assert strip_leading_noise(tokens=tokens) == (["git", "push"], False)


def test_a_bare_mise_token_with_nothing_after_it_leaves_no_command() -> None:
    assert strip_leading_noise(tokens=["mise"]) == ([], False)


def test_stacked_wrappers_are_peeled_until_no_wrapper_remains() -> None:
    tokens = ["LEFTHOOK=1", "sudo", "mise", "exec", "--", "git", "commit", "--no-verify"]

    assert strip_leading_noise(tokens=tokens) == (["git", "commit", "--no-verify"], False)


def test_a_path_qualified_binary_is_not_mistaken_for_a_wrapper() -> None:
    tokens = ["/usr/bin/git", "status"]

    assert strip_leading_noise(tokens=tokens) == (["/usr/bin/git", "status"], False)


# ---------------------------------------------------------------------------
# _git_subcommand — find the git subcommand past any global options
# ---------------------------------------------------------------------------


def test_no_tokens_is_not_a_git_invocation() -> None:
    assert git_subcommand(tokens=[]) == (None, [])


def test_a_non_git_leading_command_is_not_a_git_invocation() -> None:
    assert git_subcommand(tokens=["echo", "git", "commit"]) == (None, [])


def test_a_path_qualified_git_is_still_recognised_as_git() -> None:
    assert git_subcommand(tokens=["/usr/bin/git", "status", "-s"]) == ("status", ["-s"])


def test_a_global_option_taking_an_argument_is_skipped_with_its_argument() -> None:
    tokens = ["git", "-C", "/tmp/repo", "commit", "-m", "x"]

    assert git_subcommand(tokens=tokens) == ("commit", ["-m", "x"])


def test_a_repeated_config_override_option_is_skipped_with_its_argument() -> None:
    tokens = ["git", "-c", "user.name=Someone", "push", "--no-verify"]

    assert git_subcommand(tokens=tokens) == ("push", ["--no-verify"])


def test_a_global_flag_that_takes_no_argument_is_skipped_alone() -> None:
    assert git_subcommand(tokens=["git", "--no-pager", "log"]) == ("log", [])


def test_a_bare_double_dash_terminates_the_global_option_scan() -> None:
    assert git_subcommand(tokens=["git", "--", "status"]) == ("status", [])


def test_git_with_only_global_options_and_no_subcommand_has_no_subcommand() -> None:
    assert git_subcommand(tokens=["git", "-C", "/tmp/repo"]) == (None, [])


def test_a_trailing_argument_taking_option_with_no_argument_has_no_subcommand() -> None:
    assert git_subcommand(tokens=["git", "-C"]) == (None, [])


# ---------------------------------------------------------------------------
# _check_segment — what IS a footgun vs what merely mentions one
# ---------------------------------------------------------------------------


def test_an_unparseable_segment_fails_open() -> None:
    # An unbalanced quote makes shlex raise; a guard bug must never block work.
    assert check_segment(seg='echo "unbalanced') == (False, "")


def test_an_empty_segment_is_not_a_footgun() -> None:
    assert check_segment(seg="") == (False, "")


def test_git_commit_with_no_verify_is_blocked() -> None:
    blocked, reason = check_segment(seg="git commit --no-verify -m 'x'")

    assert blocked is True
    assert reason == guard._NO_VERIFY_REASON  # noqa: SLF001


def test_git_push_with_no_verify_is_blocked() -> None:
    blocked, reason = check_segment(seg="git push --no-verify origin master")

    assert blocked is True
    assert reason == guard._NO_VERIFY_REASON  # noqa: SLF001


def test_git_commit_without_no_verify_is_allowed() -> None:
    assert check_segment(seg="git commit -m 'a real commit'") == (False, "")


def test_a_git_subcommand_that_has_no_footgun_form_is_allowed() -> None:
    assert check_segment(seg="git status --short") == (False, "")


def test_a_lefthook_disabling_prefix_is_blocked_as_a_no_verify_equivalent() -> None:
    blocked, reason = check_segment(seg="LEFTHOOK=0 git commit -m 'x'")

    assert blocked is True
    assert reason == guard._LEFTHOOK_REASON  # noqa: SLF001


def test_reading_core_bare_with_git_config_get_is_allowed() -> None:
    assert check_segment(seg="git config --get core.bare") == (False, "")


def test_setting_core_bare_true_is_blocked() -> None:
    blocked, reason = check_segment(seg="git config core.bare true")

    assert blocked is True
    assert reason == guard._CORE_BARE_REASON  # noqa: SLF001


def test_setting_core_bare_with_an_equals_form_is_blocked() -> None:
    blocked, reason = check_segment(seg="git config core.bare=true")

    assert blocked is True
    assert reason == guard._CORE_BARE_REASON  # noqa: SLF001


def test_setting_core_bare_false_is_allowed() -> None:
    assert check_segment(seg="git config core.bare false") == (False, "")


def test_setting_an_unrelated_git_config_key_is_allowed() -> None:
    assert check_segment(seg="git config user.name Someone") == (False, "")


def test_a_non_git_command_carrying_the_dangerous_string_as_data_is_allowed() -> None:
    assert check_segment(seg='echo "git commit --no-verify"') == (False, "")


def test_a_grep_over_history_mentioning_a_footgun_is_allowed() -> None:
    assert check_segment(seg="grep -r 'git config core.bare true' docs/") == (False, "")


# ---------------------------------------------------------------------------
# main() — stdin protocol, deny payload shape, and fail-open behavior
# ---------------------------------------------------------------------------


def test_empty_stdin_exits_without_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _drive_main(payload="", monkeypatch=monkeypatch)

    assert capsys.readouterr().out == ""


def test_whitespace_only_stdin_exits_without_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _drive_main(payload="   \n  ", monkeypatch=monkeypatch)

    assert capsys.readouterr().out == ""


def test_a_non_bash_tool_is_ignored(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = json.dumps({"tool_name": "Read", "tool_input": {"command": "git push --no-verify"}})

    _drive_main(payload=payload, monkeypatch=monkeypatch)

    assert capsys.readouterr().out == ""


def test_a_bash_call_with_no_tool_input_is_ignored(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _drive_main(payload=json.dumps({"tool_name": "Bash"}), monkeypatch=monkeypatch)

    assert capsys.readouterr().out == ""


def test_a_bash_call_with_an_empty_command_is_ignored(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _drive_main(payload=_bash_payload(command=""), monkeypatch=monkeypatch)

    assert capsys.readouterr().out == ""


def test_a_clean_command_produces_no_deny_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _bash_payload(command="mise exec -- git commit -m 'real work' && git status")

    _drive_main(payload=payload, monkeypatch=monkeypatch)

    assert capsys.readouterr().out == ""


def test_a_footgun_in_a_later_segment_emits_the_deny_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    command = "git add -A && mise exec -- git commit --no-verify -m 'x'"

    _drive_main(payload=_bash_payload(command=command), monkeypatch=monkeypatch)

    emitted = json.loads(capsys.readouterr().out)
    hook_output = emitted["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    reason = hook_output["permissionDecisionReason"]
    assert reason.startswith("BLOCKED by livespec_footgun_guard.py")
    assert guard._NO_VERIFY_REASON in reason  # noqa: SLF001
    assert f"Command: {command}" in reason
    assert "Do NOT retry" in reason


def test_malformed_json_on_stdin_fails_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _drive_main(payload="{not json at all", monkeypatch=monkeypatch)

    assert capsys.readouterr().out == ""


def test_an_unexpected_runtime_error_fails_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Any non-JSON failure inside main must still exit 0 — the guard is a fast
    # early warning, never a gate that can wedge a session.
    _drive_main(payload=_ExplodingStdin(), monkeypatch=monkeypatch)

    assert capsys.readouterr().out == ""
