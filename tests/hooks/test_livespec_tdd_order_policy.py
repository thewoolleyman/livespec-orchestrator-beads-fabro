"""Coverage for the pure test-first order policy behind the TDD order guard.

The policy answers one question: may this tool write this path right now? The
discriminator is the one `red_green_replay` leg 4 already uses — HEAD's commit
message carries `TDD-Red-Test-File-Checksum:` and does NOT carry
`TDD-Green-Verified-At:` — so an existing product file is writable only while
HEAD is an open Red. These tests read as the documentation of that line.

`.claude/hooks/` is not an importable package, so the module is loaded by file
location — the same idiom `test_livespec_footgun_guard.py` uses. The import
happens INSIDE each test body via `importlib`, and the first assertion is that
the module file exists, so the Red commit fails on a genuine assertion rather
than at collection time.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_POLICY_PATH = _HOOKS_DIR / "livespec_tdd_order_policy.py"
_MODULE_NAME = "livespec_tdd_order_policy_under_test"

_RED = "TDD-Red-Test-File-Checksum: abc123"
_GREEN = "TDD-Green-Verified-At: 2026-10-01T00:00:00Z"
_PREFIXES = (".claude-plugin/scripts/livespec_orchestrator_beads_fabro/", ".claude/hooks/")


def _load_policy() -> ModuleType:
    """Load the policy module by file location, asserting it exists first."""
    assert _POLICY_PATH.is_file(), f"policy module not implemented yet: {_POLICY_PATH}"
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _POLICY_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def test_head_state_reports_open_red_for_a_red_only_message() -> None:
    policy = _load_policy()
    assert policy.head_state(message=f"feat: thing\n\n{_RED}\n") == policy.HEAD_OPEN_RED


def test_head_state_reports_closed_for_a_red_green_pair() -> None:
    policy = _load_policy()
    assert policy.head_state(message=f"feat: thing\n\n{_RED}\n{_GREEN}\n") == policy.HEAD_CLOSED


def test_head_state_reports_no_trailers_for_an_untrailered_message() -> None:
    policy = _load_policy()
    assert policy.head_state(message="chore: docs only\n") == policy.HEAD_NO_TRAILERS


def test_head_state_reports_no_trailers_for_an_unreadable_head() -> None:
    policy = _load_policy()
    assert policy.head_state(message="") == policy.HEAD_NO_TRAILERS


def test_is_product_path_accepts_a_declared_prefix_python_file() -> None:
    policy = _load_policy()
    assert policy.is_product_path(path=".claude/hooks/some_guard.py", prefixes=_PREFIXES)


def test_is_product_path_rejects_a_test_a_non_python_and_an_undeclared_tree() -> None:
    policy = _load_policy()
    assert not policy.is_product_path(path="tests/hooks/test_x.py", prefixes=_PREFIXES)
    assert not policy.is_product_path(path=".claude/hooks/notes.md", prefixes=_PREFIXES)
    assert not policy.is_product_path(path="plan/topic/research.py", prefixes=_PREFIXES)


def test_is_product_path_rejects_vendored_python() -> None:
    policy = _load_policy()
    vendored = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/_vendor/returns/result.py"
    assert not policy.is_product_path(path=vendored, prefixes=(".claude-plugin/scripts/",))


def test_relative_path_normalizes_an_absolute_in_repo_path() -> None:
    policy = _load_policy()
    absolute = f"{_REPO_ROOT}/.claude/hooks/some_guard.py"
    assert policy.relative_path(path=absolute, repo_root=str(_REPO_ROOT)) == (
        ".claude/hooks/some_guard.py"
    )


def test_relative_path_passes_through_an_already_relative_path() -> None:
    policy = _load_policy()
    assert policy.relative_path(path="./.claude/hooks/g.py", repo_root="/repo") == (
        ".claude/hooks/g.py"
    )


def test_relative_path_passes_through_a_path_outside_the_repo_root() -> None:
    policy = _load_policy()
    assert policy.relative_path(path="/etc/passwd", repo_root="/repo") == "/etc/passwd"


def test_decide_refuses_an_existing_product_write_at_a_closed_head() -> None:
    policy = _load_policy()
    decision = policy.decide(
        tool="Write",
        path=".claude/hooks/some_guard.py",
        head_state=policy.HEAD_CLOSED,
        exists_at_head=True,
        test_change_pending=False,
    )
    assert decision.decision == policy.REFUSE
    assert decision.reason == policy.REASON_CLOSED_HEAD
    assert decision.head_state == policy.HEAD_CLOSED
    assert decision.tool == "Write"
    assert decision.path == ".claude/hooks/some_guard.py"


def test_decide_refuses_an_existing_product_write_at_a_trailer_free_head() -> None:
    policy = _load_policy()
    decision = policy.decide(
        tool="Edit",
        path=".claude/hooks/some_guard.py",
        head_state=policy.HEAD_NO_TRAILERS,
        exists_at_head=True,
        test_change_pending=True,
    )
    assert decision.decision == policy.REFUSE
    assert decision.reason == policy.REASON_TRAILER_FREE_HEAD


def test_decide_refuses_a_multiedit_the_same_way_as_a_write() -> None:
    policy = _load_policy()
    decision = policy.decide(
        tool="MultiEdit",
        path=".claude/hooks/some_guard.py",
        head_state=policy.HEAD_CLOSED,
        exists_at_head=True,
        test_change_pending=False,
    )
    assert decision.decision == policy.REFUSE


def test_decide_allows_any_product_write_while_head_is_an_open_red() -> None:
    policy = _load_policy()
    decision = policy.decide(
        tool="Write",
        path=".claude/hooks/some_guard.py",
        head_state=policy.HEAD_OPEN_RED,
        exists_at_head=True,
        test_change_pending=False,
    )
    assert decision.decision == policy.ALLOW
    assert decision.reason == policy.REASON_OPEN_RED


def test_refusal_message_names_the_required_open_red_state_and_both_trailers() -> None:
    policy = _load_policy()
    decision = policy.decide(
        tool="Write",
        path=".claude/hooks/some_guard.py",
        head_state=policy.HEAD_CLOSED,
        exists_at_head=True,
        test_change_pending=False,
    )
    message = policy.refusal_message(decision=decision)
    assert "open Red" in message
    assert "TDD-Red-Test-File-Checksum:" in message
    assert "TDD-Green-Verified-At:" in message
    assert ".claude/hooks/some_guard.py" in message
    assert policy.HEAD_CLOSED in message


def test_refusal_message_states_the_new_module_stub_carveout() -> None:
    policy = _load_policy()
    decision = policy.decide(
        tool="Write",
        path=".claude/hooks/new_guard.py",
        head_state=policy.HEAD_CLOSED,
        exists_at_head=False,
        test_change_pending=False,
    )
    assert decision.reason == policy.REASON_STUB_WITHOUT_PENDING_TEST
    assert "new-module" in policy.refusal_message(decision=decision)


def test_refusal_message_is_deterministic_across_repeated_calls() -> None:
    policy = _load_policy()
    decision = policy.decide(
        tool="Write",
        path=".claude/hooks/some_guard.py",
        head_state=policy.HEAD_NO_TRAILERS,
        exists_at_head=True,
        test_change_pending=False,
    )
    assert policy.refusal_message(decision=decision) == policy.refusal_message(decision=decision)
