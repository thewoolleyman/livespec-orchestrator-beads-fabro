"""livespec TDD order guard — Claude Code PreToolUse hook.

Refuses a write to a PRODUCT path unless the repository is in a state where
test-first work permits it. The `red_green_replay` commit-msg hook enforces a
commit SHAPE and a shape can be produced after the fact — the implementation
written first, the Red cut afterwards by moving it aside — so nothing in the
pipeline has ever observed the ORDER of work. The measurement that motivated
this guard, including the fleet-wide Red-to-Green interval that exposed the
pattern, is in
`plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md`.

This module is the IO half: it reads HEAD's commit message, asks whether the
target exists at HEAD, and asks whether a test change is uncommitted, then
hands those three answers to `livespec_tdd_order_policy`. The write targets
themselves come from `livespec_tdd_order_targets`, which covers the structured
`Write`/`Edit`/`MultiEdit` surface and the shell write forms alike — so a
`Bash` redirection into a product path gets the same verdict a `Write` would.

The two fail directions are deliberately ASYMMETRIC, and the distinction is
the whole safety argument:

- The DECISION is fail-CLOSED. An unreadable HEAD classifies as trailer-free
  and REFUSES; it does not admit a product write on a repository the guard
  cannot see. The one sanctioned fail-open inside the decision is the Bash
  tokenizer (see `livespec_tdd_order_targets.shell_write_targets`), because a
  lexer error must not refuse legitimate work.
- The HOOK is fail-OPEN at its boundary. A bug in this guard passes through
  silently, because a crashing PreToolUse hook wedges every tool call in the
  session. That is the sole broad catch in this artifact.

Product paths are resolved through the PUBLIC
`livespec_dev_tooling.config.derive_source_prefixes` — the same derivation
`red_green_replay` delegates to — so this guard and the commit-msg gate cannot
disagree about what counts as product. The guard therefore governs its own
source tree, which is the intended dogfood.

Always exits 0: a deny is expressed in the hook's JSON payload on stdout, not
in the exit status.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import livespec_tdd_order_policy as policy
import livespec_tdd_order_span as span
import livespec_tdd_order_targets as targets
from livespec_dev_tooling.config import derive_source_prefixes, load_config

__all__: list[str] = ["main"]

_PROJECT_DIR_ENV_VAR = "CLAUDE_PROJECT_DIR"
_TESTS_TREE = "tests"
_PYTHON_SUFFIX = ".py"
_GIT_TIMEOUT_SECONDS = 15.0
_PORCELAIN_STATUS_WIDTH = 3


def main() -> int:
    """Read the PreToolUse payload on stdin and deny an out-of-order write."""
    try:
        return _run(raw=sys.stdin.read(), environ=dict(os.environ))
    # The BOUNDARY is fail-open even though the DECISION is fail-closed: a bug
    # in this guard must not wedge every tool call in the session. The
    # fail-closed half lives in `_head_message`, which substitutes the empty
    # message `policy.head_state` reads as trailer-free.
    except Exception:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        return 0


def _run(*, raw: str, environ: dict[str, str]) -> int:
    """Emit the deny payload for the first out-of-order product write.

    Every verdict over a product path — allow as well as refuse — is traced
    before it is acted on, so the refusal rate is queryable rather than
    anecdotal. A path that is NOT a product path is not a verdict of this
    guard and is not traced. The loop stops at the first refusal, so any
    target behind it is left undecided and untraced.
    """
    payload = _payload(raw=raw)
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return 0
    requested = targets.write_targets(tool_name=tool_name, tool_input=tool_input)
    if not requested:
        return 0
    repo_root = _repo_root(environ=environ)
    product_paths = _product_paths(paths=requested, repo_root=repo_root)
    if not product_paths:
        return 0
    head_state = policy.head_state(message=_head_message(repo_root=repo_root))
    test_change_pending = _test_change_pending(repo_root=repo_root)
    for path in product_paths:
        decision = policy.decide(
            tool=tool_name,
            path=path,
            head_state=head_state,
            exists_at_head=_exists_at_head(repo_root=repo_root, path=path),
            test_change_pending=test_change_pending,
        )
        _ = span.emit_for_decision(decision=decision, environ=environ)
        if decision.decision == policy.REFUSE:
            _ = sys.stdout.write(_deny_payload(decision=decision) + "\n")
            return 0
    return 0


def _payload(*, raw: str) -> dict[str, object]:
    """Parse the hook payload, or return an empty mapping for unusable input."""
    if not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _product_paths(*, paths: list[str], repo_root: Path) -> list[str]:
    """Normalize requested write targets and keep the product-path ones."""
    prefixes = derive_source_prefixes(config=load_config(repo_root=repo_root))
    relative = (policy.relative_path(path=path, repo_root=str(repo_root)) for path in paths)
    return [path for path in relative if policy.is_product_path(path=path, prefixes=prefixes)]


def _deny_payload(*, decision: policy.Decision) -> str:
    """Render the PreToolUse deny payload for one refused decision."""
    reason = policy.refusal_message(decision=decision)
    return json.dumps(
        {
            "decision": "block",
            "reason": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        }
    )


def _repo_root(*, environ: dict[str, str]) -> Path:
    """Resolve the governed repository root Claude Code is operating on."""
    declared = environ.get(_PROJECT_DIR_ENV_VAR, "").strip()
    if declared:
        return Path(declared)
    returncode, stdout = _git(repo_root=Path.cwd(), arguments=["rev-parse", "--show-toplevel"])
    resolved = stdout.strip()
    return Path(resolved) if returncode == 0 and resolved else Path.cwd()


def _head_message(*, repo_root: Path) -> str:
    """Return HEAD's full commit message, or empty when it cannot be read.

    Empty is the FAIL-CLOSED value: `policy.head_state` classifies it as
    trailer-free, which refuses a product write.
    """
    returncode, stdout = _git(repo_root=repo_root, arguments=["log", "-1", "--format=%B"])
    return stdout if returncode == 0 else ""


def _exists_at_head(*, repo_root: Path, path: str) -> bool:
    """True iff `path` is present in HEAD's tree."""
    returncode, _ = _git(repo_root=repo_root, arguments=["cat-file", "-e", f"HEAD:{path}"])
    return returncode == 0


def _test_change_pending(*, repo_root: Path) -> bool:
    """True iff an uncommitted Python change sits under the tests tree.

    This is the second half of the new-module stub carveout: a product file
    that does not exist at HEAD may be created while its test is being
    written. A modified AND an untracked test both count, which is why this
    reads `status --porcelain` rather than a diff.
    """
    returncode, stdout = _git(
        repo_root=repo_root, arguments=["status", "--porcelain", "--", _TESTS_TREE]
    )
    if returncode != 0:
        return False
    return any(
        line[_PORCELAIN_STATUS_WIDTH:].strip().endswith(_PYTHON_SUFFIX)
        for line in stdout.splitlines()
        if line.strip()
    )


def _git(*, repo_root: Path, arguments: list[str]) -> tuple[int, str]:
    """Run one read-only git command; return its return code and stdout.

    A git that cannot run at all reports a non-zero code and no output, so
    every caller resolves to its own fail-closed value rather than raising
    into the hook's boundary.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return completed.returncode, completed.stdout


if __name__ == "__main__":
    raise SystemExit(main())
