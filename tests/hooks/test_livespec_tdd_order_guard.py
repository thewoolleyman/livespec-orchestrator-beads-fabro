"""Coverage for the TDD order guard — a Claude Code PreToolUse hook.

The guard is the one place the pure policy meets real repository state. It
reads HEAD's commit message, asks whether the target exists at HEAD, and asks
whether a test change is uncommitted; those three answers drive the decision
table in `livespec_tdd_order_policy`. These tests therefore drive `main()`
in-process against REAL throwaway git repositories, because the git reads are
the behaviour under test and a seam over them would prove nothing.

Two fail directions, deliberately asymmetric, and both are asserted here:

- The DECISION is fail-CLOSED. An unreadable HEAD classifies as trailer-free
  and refuses, rather than admitting a product write on a repository the guard
  cannot see.
- The HOOK is fail-OPEN. Malformed input, an unmodelled payload shape, or a
  bug inside the guard passes through silently, because a crashing PreToolUse
  hook wedges every tool call in the session.

`.claude/hooks/` is not an importable package and the guard imports its two
sibling modules the way a script does — off the directory it lives in — so
that directory is put on `sys.path` before the module is loaded by file
location. The load happens INSIDE each test body, and the first assertion is
that the file exists, so the Red commit fails on a genuine assertion rather
than at collection time.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_GUARD_PATH = _HOOKS_DIR / "livespec_tdd_order_guard.py"
_MODULE_NAME = "livespec_tdd_order_guard_under_test"

_PRODUCT_PATH = "hooks/some_guard.py"
_OTHER_PRODUCT_PATH = "hooks/other_guard.py"
_TEST_PATH = "tests/hooks/test_some_guard.py"
_RED_TRAILER = "TDD-Red-Test-File-Checksum: sha256:abc"
_GREEN_TRAILER = "TDD-Green-Verified-At: 2026-10-01T00:00:00Z"
_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
_PARENT_SPAN_ID = "00f067aa0ba902b7"

_FIXTURE_PYPROJECT = """\
[project]
name = "fixture"
version = "0.0.0"

[tool.livespec_dev_tooling]
source_trees = ["hooks"]
source_tree_prefixes = ["hooks/"]
"""


def _load_guard() -> ModuleType:
    """Load the guard by file location, asserting it exists first."""
    assert _GUARD_PATH.is_file(), f"guard not implemented yet: {_GUARD_PATH}"
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _GUARD_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _git(*, repo: Path, arguments: list[str]) -> None:
    _ = subprocess.run(["git", "-C", str(repo), *arguments], check=True, capture_output=True)


def _write(*, repo: Path, relative: str, body: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(body, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repository shaped like a governed livespec consumer."""
    _git(repo=tmp_path, arguments=["init", "--quiet"])
    _git(repo=tmp_path, arguments=["config", "user.email", "fixture@example.com"])
    _git(repo=tmp_path, arguments=["config", "user.name", "Fixture"])
    _write(repo=tmp_path, relative="pyproject.toml", body=_FIXTURE_PYPROJECT)
    _write(repo=tmp_path, relative=_TEST_PATH, body="def test_x() -> None:\n    assert True\n")
    _git(repo=tmp_path, arguments=["add", "-A"])
    _git(repo=tmp_path, arguments=["commit", "--quiet", "-m", "chore: fixture baseline"])
    return tmp_path


def _commit_product(*, repo: Path, message: str) -> None:
    """Land the product path at HEAD under a commit carrying `message`."""
    _write(repo=repo, relative=_PRODUCT_PATH, body="VALUE = 1\n")
    _write(repo=repo, relative=_OTHER_PRODUCT_PATH, body="OTHER = 1\n")
    _git(repo=repo, arguments=["add", "-A"])
    _git(repo=repo, arguments=["commit", "--quiet", "-m", message])


def _drive(
    *,
    guard: ModuleType,
    payload: object,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object] | None:
    """Run `main()` in-process; return the parsed deny payload, or None."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    assert guard.main() == 0
    captured = capsys.readouterr().out.strip()
    return json.loads(captured) if captured else None


def _structured(*, tool: str, path: str) -> dict[str, object]:
    return {"tool_name": tool, "tool_input": {"file_path": path}}


def _bash(*, command: str) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


# --- the refusal, on every structured write tool ---------------------------


@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_an_existing_product_write_at_a_closed_head_is_refused(
    tool: str, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    denial = _drive(
        guard=guard,
        payload=_structured(tool=tool, path=_PRODUCT_PATH),
        repo=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None
    assert denial["decision"] == "block"
    hook_output = denial["hookSpecificOutput"]
    assert isinstance(hook_output, dict)
    assert hook_output["permissionDecision"] == "deny"
    assert hook_output["hookEventName"] == "PreToolUse"
    reason = hook_output["permissionDecisionReason"]
    assert isinstance(reason, str)
    assert "open Red" in reason
    assert _PRODUCT_PATH in reason
    assert tool in reason


def test_an_existing_product_write_at_a_trailer_free_head_is_refused(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message="chore: no trailers here")
    denial = _drive(
        guard=guard,
        payload=_structured(tool="Write", path=_PRODUCT_PATH),
        repo=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None
    assert "trailer-free-head" in str(denial["reason"])


def test_an_absolute_product_path_is_refused_the_same_as_a_relative_one(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    denial = _drive(
        guard=guard,
        payload=_structured(tool="Write", path=str(repo / _PRODUCT_PATH)),
        repo=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None
    assert _PRODUCT_PATH in str(denial["reason"])


# --- the allow, while HEAD is an open Red ----------------------------------


def test_an_existing_product_write_while_head_is_an_open_red_is_allowed(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n")
    assert (
        _drive(
            guard=guard,
            payload=_structured(tool="Write", path=_PRODUCT_PATH),
            repo=repo,
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        is None
    )


def test_several_product_targets_are_all_allowed_while_head_is_an_open_red(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n")
    command = f"echo a > {_PRODUCT_PATH}; echo b > {_OTHER_PRODUCT_PATH}"
    assert (
        _drive(
            guard=guard,
            payload=_bash(command=command),
            repo=repo,
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        is None
    )


# --- the Bash leg decides identically -------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        f"echo x > {_PRODUCT_PATH}",
        f"echo x >> {_PRODUCT_PATH}",
        f"echo x | tee {_PRODUCT_PATH}",
        f"sed -i s/a/b/ {_PRODUCT_PATH}",
        f"cp donor.py {_PRODUCT_PATH}",
        f"mv donor.py {_PRODUCT_PATH}",
        f"cat > {_PRODUCT_PATH} <<'EOF'\nVALUE = 2\nEOF",
    ],
)
def test_a_shell_write_into_a_product_path_at_a_closed_head_is_refused(
    command: str, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    denial = _drive(
        guard=guard,
        payload=_bash(command=command),
        repo=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None
    assert _PRODUCT_PATH in str(denial["reason"])
    assert "Bash" in str(denial["reason"])


def test_a_non_product_shell_target_does_not_mask_a_product_one_behind_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    command = f"echo x > README.md; echo y > {_PRODUCT_PATH}"
    denial = _drive(
        guard=guard,
        payload=_bash(command=command),
        repo=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None
    assert _PRODUCT_PATH in str(denial["reason"])


# --- the new-module stub carveout ------------------------------------------


def test_a_missing_at_head_stub_with_an_uncommitted_test_change_is_allowed(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    _write(repo=repo, relative=_TEST_PATH, body="def test_x() -> None:\n    assert False\n")
    assert (
        _drive(
            guard=guard,
            payload=_structured(tool="Write", path="hooks/brand_new.py"),
            repo=repo,
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        is None
    )


def test_an_untracked_new_test_file_also_opens_the_carveout(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    _write(repo=repo, relative="tests/hooks/test_brand_new.py", body="def test_y() -> None: ...\n")
    assert (
        _drive(
            guard=guard,
            payload=_structured(tool="Write", path="hooks/brand_new.py"),
            repo=repo,
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        is None
    )


def test_a_missing_at_head_stub_with_no_pending_test_change_is_refused(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    denial = _drive(
        guard=guard,
        payload=_structured(tool="Write", path="hooks/brand_new.py"),
        repo=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None
    assert "stub-without-pending-test" in str(denial["reason"])


def test_an_uncommitted_non_python_change_under_tests_does_not_open_the_carveout(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    _write(repo=repo, relative="tests/hooks/fixture.json", body="{}\n")
    denial = _drive(
        guard=guard,
        payload=_structured(tool="Write", path="hooks/brand_new.py"),
        repo=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None
    assert "stub-without-pending-test" in str(denial["reason"])


# --- everything the guard must leave alone ---------------------------------


@pytest.mark.parametrize(
    "path",
    ["tests/hooks/test_some_guard.py", "README.md", "plan/topic/notes.py", "hooks/notes.md"],
)
def test_a_write_outside_the_product_universe_is_allowed(
    path: str, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message="chore: no trailers here")
    assert (
        _drive(
            guard=guard,
            payload=_structured(tool="Write", path=path),
            repo=repo,
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        is None
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "Read", "tool_input": {"file_path": _PRODUCT_PATH}},
        {"tool_name": "Bash", "tool_input": {"command": f"cat {_PRODUCT_PATH}"}},
        {"tool_name": "Write", "tool_input": "not-a-mapping"},
        {"tool_name": "Write"},
        {},
        "[]",
        "",
        "   ",
        "{not json",
    ],
)
def test_an_unmodelled_or_malformed_payload_passes_through(
    payload: object,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message="chore: no trailers here")
    assert (
        _drive(guard=guard, payload=payload, repo=repo, monkeypatch=monkeypatch, capsys=capsys)
        is None
    )


def test_a_bug_inside_the_guard_passes_through_rather_than_wedging_the_session(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))

    class _ExplodingStdin:
        def read(self) -> str:
            raise RuntimeError("guard bug")

    monkeypatch.setattr(sys, "stdin", _ExplodingStdin())
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


# --- repo-root resolution and the fail-CLOSED decision --------------------


def test_the_repo_root_falls_back_to_git_when_the_project_dir_is_unset(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps(_structured(tool="Write", path=_PRODUCT_PATH)))
    )
    assert guard.main() == 0
    captured = capsys.readouterr().out.strip()
    assert captured
    assert "open Red" in captured


def test_a_blank_project_dir_is_treated_as_unset(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "   ")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps(_structured(tool="Write", path=_PRODUCT_PATH)))
    )
    assert guard.main() == 0
    assert capsys.readouterr().out.strip()


def test_an_unreadable_git_refuses_rather_than_admitting_the_write(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n")

    def _unavailable(*_args: object, **_kwargs: object) -> object:
        raise OSError("git is not installed")

    monkeypatch.setattr(guard.subprocess, "run", _unavailable)
    denial = _drive(
        guard=guard,
        payload=_structured(tool="Write", path=_PRODUCT_PATH),
        repo=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None
    assert "no-trailers" in str(denial["reason"])


def test_a_project_dir_that_is_not_a_repository_refuses_rather_than_admitting(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A git command that EXITS non-zero resolves to the fail-closed value.

    The directory has to sit OUTSIDE the fixture repository: git walks upward
    from `-C`, so a subdirectory of a repository is still in that repository
    and every read would succeed.
    """
    guard = _load_guard()
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n")
    not_a_repo = repo.parent / "outside-any-repository"
    not_a_repo.mkdir(exist_ok=True)
    _write(repo=not_a_repo, relative="pyproject.toml", body=_FIXTURE_PYPROJECT)
    denial = _drive(
        guard=guard,
        payload=_structured(tool="Write", path=_PRODUCT_PATH),
        repo=not_a_repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None
    assert "no-trailers" in str(denial["reason"])


# --- telemetry: one span per decision -------------------------------------


class _FakeResponse:
    def __init__(self, *, status: int) -> None:
        self.status = status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _capture_posts(*, guard: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Intercept the span exporter's POSTs and return the captured list."""
    posted: list[Any] = []

    def _urlopen(request: Any, timeout: float) -> _FakeResponse:  # noqa: ARG001
        posted.append(request)
        return _FakeResponse(status=200)

    monkeypatch.setattr(guard.span.urllib.request, "urlopen", _urlopen)
    return posted


def _posted_attributes(*, request: Any) -> dict[str, Any]:
    body = json.loads(request.data.decode("utf-8"))
    emitted = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    return {entry["key"]: entry["value"]["stringValue"] for entry in emitted["attributes"]}


def test_a_refusal_emits_one_decision_span_on_the_runs_trace(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    posted = _capture_posts(guard=guard, monkeypatch=monkeypatch)
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    monkeypatch.setenv(guard.span.ENDPOINT_ENV_VAR, "http://172.17.0.1:4318")
    monkeypatch.setenv(guard.span.TRACE_CONTEXT_ENV_VAR, f"00-{_TRACE_ID}-{_PARENT_SPAN_ID}-01")

    denial = _drive(
        guard=guard,
        payload=_structured(tool="Write", path=_PRODUCT_PATH),
        repo=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None
    assert len(posted) == 1
    assert posted[0].full_url == "http://172.17.0.1:4318/v1/traces"

    attributes = _posted_attributes(request=posted[0])
    assert attributes["tdd.decision"] == "refuse"
    assert attributes["tdd.path"] == _PRODUCT_PATH
    assert attributes["tdd.head_state"] == "closed"
    assert attributes["tdd.reason"] == "closed-head"
    assert attributes["tdd.tool"] == "Write"

    body = json.loads(posted[0].data.decode("utf-8"))
    emitted = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert emitted["traceId"] == _TRACE_ID
    assert emitted["parentSpanId"] == _PARENT_SPAN_ID


def test_an_allow_also_emits_a_decision_span(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    posted = _capture_posts(guard=guard, monkeypatch=monkeypatch)
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n")
    monkeypatch.setenv(guard.span.ENDPOINT_ENV_VAR, "http://172.17.0.1:4318")

    assert (
        _drive(
            guard=guard,
            payload=_structured(tool="Edit", path=_PRODUCT_PATH),
            repo=repo,
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        is None
    )
    assert len(posted) == 1
    attributes = _posted_attributes(request=posted[0])
    assert attributes["tdd.decision"] == "allow"
    assert attributes["tdd.reason"] == "open-red"
    assert attributes["tdd.tool"] == "Edit"


def test_a_write_outside_the_product_universe_emits_no_span(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-product write is not a decision of this guard, so it is not a span.

    The positive control below is what makes the empty list evidence: the same
    interception records a post for a product path in the same test.
    """
    guard = _load_guard()
    posted = _capture_posts(guard=guard, monkeypatch=monkeypatch)
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n")
    monkeypatch.setenv(guard.span.ENDPOINT_ENV_VAR, "http://172.17.0.1:4318")

    assert (
        _drive(
            guard=guard,
            payload=_structured(tool="Write", path="README.md"),
            repo=repo,
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        is None
    )
    assert posted == []

    assert (
        _drive(
            guard=guard,
            payload=_structured(tool="Write", path=_PRODUCT_PATH),
            repo=repo,
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        is None
    )
    assert len(posted) == 1


def test_no_span_is_posted_when_no_sandbox_endpoint_is_configured(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load_guard()
    posted = _capture_posts(guard=guard, monkeypatch=monkeypatch)
    _commit_product(repo=repo, message=f"feat: thing\n\n{_RED_TRAILER}\n{_GREEN_TRAILER}\n")
    monkeypatch.delenv(guard.span.ENDPOINT_ENV_VAR, raising=False)

    denial = _drive(
        guard=guard,
        payload=_structured(tool="Write", path=_PRODUCT_PATH),
        repo=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert denial is not None, "the refusal must stand with or without telemetry"
    assert posted == []


# --- registration: the guard is actually wired to the tool surface --------


def test_the_guard_is_registered_as_a_pretooluse_hook_on_every_write_surface() -> None:
    """An unregistered guard is an unarmed guard, so the wiring is asserted.

    The matcher has to name the three structured write tools AND `Bash`: the
    shell write forms are exactly the leg a structured-only matcher would miss.
    """
    settings = json.loads((_REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for entry in settings["hooks"]["PreToolUse"]
        for hook in entry["hooks"]
        if "livespec_tdd_order_guard.py" in hook["command"]
    ]
    assert len(commands) == 1, "the guard must be registered exactly once"

    matchers = [
        entry["matcher"]
        for entry in settings["hooks"]["PreToolUse"]
        for hook in entry["hooks"]
        if "livespec_tdd_order_guard.py" in hook["command"]
    ]
    assert len(matchers) == 1
    for tool in ("Write", "Edit", "MultiEdit", "Bash"):
        assert tool in matchers[0]
