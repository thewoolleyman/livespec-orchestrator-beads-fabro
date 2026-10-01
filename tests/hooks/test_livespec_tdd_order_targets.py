"""Coverage for write-target extraction behind the TDD order guard.

One concern, two surfaces. A structured `Write`/`Edit`/`MultiEdit` names its
target outright; a `Bash` command has its targets PARSED out of five shell
write forms — `>`/`>>` redirection (which also covers a here-doc, whose
redirection sits on the introducing line), `tee`, in-place `sed`, and the last
operand of `cp`/`mv`/`install`. Both surfaces return the same shape, which is
what lets the guard apply ONE decision table to both; the parity tests at the
bottom are the assertion that it does.

`.claude/hooks/` is not an importable package, so each module under test is
loaded by file location — the same idiom `test_livespec_footgun_guard.py` uses.
The import happens INSIDE each test body via `importlib`, and the first
assertion is that the module file exists, so the Red commit fails on a genuine
assertion rather than at collection time.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_TARGETS_PATH = _HOOKS_DIR / "livespec_tdd_order_targets.py"
_POLICY_PATH = _HOOKS_DIR / "livespec_tdd_order_policy.py"

_PREFIXES = (".claude-plugin/scripts/livespec_orchestrator_beads_fabro/", ".claude/hooks/")


def _load(*, path: Path, name: str) -> ModuleType:
    """Load a hook module by file location, asserting it exists first."""
    assert path.is_file(), f"module not implemented yet: {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_targets() -> ModuleType:
    return _load(path=_TARGETS_PATH, name="livespec_tdd_order_targets_under_test")


def _load_policy() -> ModuleType:
    return _load(path=_POLICY_PATH, name="livespec_tdd_order_policy_for_parity")


def test_the_module_declares_its_write_target_extraction_surface() -> None:
    targets = _load_targets()
    assert "write_targets" in targets.__all__
    assert "shell_write_targets" in targets.__all__
    assert "STRUCTURED_WRITE_TOOLS" in targets.__all__


# --- the structured tools --------------------------------------------------


@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_write_targets_reads_file_path_from_every_structured_write_tool(tool: str) -> None:
    targets = _load_targets()
    assert tool in targets.STRUCTURED_WRITE_TOOLS
    assert targets.write_targets(tool_name=tool, tool_input={"file_path": "a/b.py"}) == ["a/b.py"]


def test_write_targets_is_empty_for_a_structured_call_with_no_usable_file_path() -> None:
    targets = _load_targets()
    assert targets.write_targets(tool_name="Write", tool_input={}) == []
    assert targets.write_targets(tool_name="Write", tool_input={"file_path": ""}) == []
    assert targets.write_targets(tool_name="Write", tool_input={"file_path": 7}) == []


def test_write_targets_is_empty_for_a_tool_that_writes_no_file() -> None:
    targets = _load_targets()
    assert targets.write_targets(tool_name="Read", tool_input={"file_path": "a/b.py"}) == []


def test_write_targets_is_empty_for_a_bash_call_with_no_usable_command() -> None:
    targets = _load_targets()
    assert targets.write_targets(tool_name="Bash", tool_input={}) == []
    assert targets.write_targets(tool_name="Bash", tool_input={"command": 7}) == []


def test_write_targets_routes_bash_through_the_shell_parser() -> None:
    targets = _load_targets()
    assert targets.write_targets(tool_name="Bash", tool_input={"command": "echo x > a/b.py"}) == [
        "a/b.py"
    ]


# --- the shell write forms -------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("echo x > a/b.py", ["a/b.py"]),
        ("echo x >a/b.py", ["a/b.py"]),
        ("echo x >> a/b.py", ["a/b.py"]),
        ("python m.py 2> a/b.py", ["a/b.py"]),
        ("echo x | tee a/b.py", ["a/b.py"]),
        ("echo x | tee -a a/b.py c/d.py", ["a/b.py", "c/d.py"]),
        ("sed -i s/a/b/ a/b.py", ["a/b.py"]),
        ("sed -i.bak s/a/b/ a/b.py", ["a/b.py"]),
        ("sed -ni p a/b.py", ["a/b.py"]),
        ("sed --in-place s/a/b/ a/b.py", ["a/b.py"]),
        ("sed --in-place=.bak s/a/b/ a/b.py", ["a/b.py"]),
        ("sed -i -e s/a/b/ a/b.py", ["a/b.py"]),
        ("sed -i -f script.sed a/b.py", ["a/b.py"]),
        ("cp src.py a/b.py", ["a/b.py"]),
        ("cp -r src.py a/b.py", ["a/b.py"]),
        ("mv src.py a/b.py", ["a/b.py"]),
        ("install -m 644 src.py a/b.py", ["a/b.py"]),
        ("/usr/bin/tee a/b.py", ["a/b.py"]),
        ("sudo tee a/b.py", ["a/b.py"]),
        ("env FOO=1 tee a/b.py", ["a/b.py"]),
        ("FOO=1 tee a/b.py", ["a/b.py"]),
        ("mise exec -- tee a/b.py", ["a/b.py"]),
        ("true && echo x > a/b.py", ["a/b.py"]),
        ("echo x > a/b.py; echo y > c/d.py", ["a/b.py", "c/d.py"]),
    ],
)
def test_shell_write_targets_recognizes_every_covered_write_form(
    command: str, expected: list[str]
) -> None:
    targets = _load_targets()
    assert targets.shell_write_targets(command=command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "cat a/b.py",
        "sed s/a/b/ a/b.py",
        "sed -n p a/b.py",
        "sed -e s/i/j/ a/b.py",
        "grep -r pattern .",
        "python -m pytest tests/",
        "echo 'cp src.py a/b.py'",
        "git log --grep='tee a/b.py'",
        "cp -r",
        "FOO=1 BAR=2",
        "echo x >",
    ],
)
def test_shell_write_targets_is_empty_for_a_command_that_writes_no_named_path(
    command: str,
) -> None:
    targets = _load_targets()
    assert targets.shell_write_targets(command=command) == []


def test_shell_write_targets_keeps_the_heredoc_redirection_and_drops_its_body() -> None:
    targets = _load_targets()
    command = "cat > a/b.py <<'EOF'\nprint('x')\ncp decoy.py c/d.py\nEOF"
    assert targets.shell_write_targets(command=command) == ["a/b.py"]


def test_shell_write_targets_handles_an_indented_heredoc_terminator() -> None:
    targets = _load_targets()
    command = "cat > a/b.py <<-EOF\n\tcp decoy.py c/d.py\n\tEOF"
    assert targets.shell_write_targets(command=command) == ["a/b.py"]


def test_shell_write_targets_handles_a_heredoc_that_never_terminates() -> None:
    targets = _load_targets()
    command = "cat > a/b.py <<'EOF'\ncp decoy.py c/d.py"
    assert targets.shell_write_targets(command=command) == ["a/b.py"]


def test_shell_write_targets_resumes_parsing_after_a_terminated_heredoc() -> None:
    targets = _load_targets()
    command = "cat > a/b.py <<'EOF'\ncp decoy.py z/z.py\nEOF\ntee c/d.py"
    assert targets.shell_write_targets(command=command) == ["a/b.py", "c/d.py"]


def test_shell_write_targets_skips_a_line_whose_quote_spans_lines() -> None:
    targets = _load_targets()
    assert targets.shell_write_targets(command='echo "spanning\nquote" > a/b.py') == []


def test_shell_write_targets_fails_open_on_an_untokenizable_command() -> None:
    targets = _load_targets()
    assert targets.shell_write_targets(command="echo 'unbalanced > a/b.py") == []


def test_shell_write_targets_fails_open_on_an_untokenizable_heredoc_line() -> None:
    targets = _load_targets()
    assert targets.shell_write_targets(command='echo "unterminated\nsecond > a/b.py') == []


# --- parity: a parsed shell target decides exactly as a structured one -----


@pytest.mark.parametrize("prefix", list(_PREFIXES))
@pytest.mark.parametrize("head", ["closed", "no-trailers", "open-red"])
def test_a_parsed_shell_target_decides_identically_to_a_structured_write(
    prefix: str, head: str
) -> None:
    targets = _load_targets()
    policy = _load_policy()
    path = f"{prefix}thing.py"
    assert policy.is_product_path(path=path, prefixes=_PREFIXES)

    from_shell = targets.shell_write_targets(command=f"echo x > {path}")
    from_structured = targets.write_targets(tool_name="Write", tool_input={"file_path": path})
    assert from_shell == from_structured == [path]

    kwargs = {
        "path": path,
        "head_state": head,
        "exists_at_head": True,
        "test_change_pending": False,
    }
    bash_decision = policy.decide(tool="Bash", **kwargs)
    write_decision = policy.decide(tool="Write", **kwargs)
    assert bash_decision.decision == write_decision.decision
    assert bash_decision.reason == write_decision.reason


@pytest.mark.parametrize(
    "command",
    [
        "echo x > .claude/hooks/thing.py",
        "tee .claude/hooks/thing.py",
        "sed -i s/a/b/ .claude/hooks/thing.py",
        "cp src.py .claude/hooks/thing.py",
        "mv src.py .claude/hooks/thing.py",
    ],
)
def test_every_shell_write_form_reaches_the_same_refusal_as_a_structured_write(
    command: str,
) -> None:
    targets = _load_targets()
    policy = _load_policy()
    path = ".claude/hooks/thing.py"

    parsed = targets.shell_write_targets(command=command)
    assert parsed == [path]
    assert policy.is_product_path(path=path, prefixes=_PREFIXES)

    decision = policy.decide(
        tool="Bash",
        path=path,
        head_state=policy.HEAD_CLOSED,
        exists_at_head=True,
        test_change_pending=False,
    )
    assert decision.decision == policy.REFUSE
    assert decision.reason == policy.REASON_CLOSED_HEAD
