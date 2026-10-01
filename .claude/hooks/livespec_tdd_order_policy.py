"""Pure test-first order policy for the livespec TDD order guard.

The guard this module decides for (`livespec_tdd_order_guard.py`) enforces the
ORDER of work the `red_green_replay` commit-msg hook cannot see. That hook
inspects staged bytes at two moments and therefore accepts a commit shape
produced AFTER the implementation was written; the measurement that motivated
this guard is recorded in
`plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md`.

The rule, in one sentence: an EXISTING product file may be written only while
HEAD is an open Red, and the only product write permitted outside an open Red
is a new-module failing stub paired with an uncommitted test change.

"Open Red" is the same discriminator `red_green_replay` leg 4 uses — HEAD's
commit message carries `TDD-Red-Test-File-Checksum:` and does NOT carry
`TDD-Green-Verified-At:`. The trailer keys are restated here rather than
imported because they are module-private to that check; the PRODUCT-PATH
model is NOT restated — `livespec_tdd_order_guard` resolves it through the
public `livespec_dev_tooling.config.derive_source_prefixes`, which is the one
derivation `red_green_replay._derive_impl_prefixes` itself delegates to, so the
two gates cannot disagree about what counts as product.

Everything here is PURE: the git reads, the environment and the hook-protocol
stdout contract live in the guard entry module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from livespec_dev_tooling.config import is_vendored_path

__all__: list[str] = [
    "ALLOW",
    "GREEN_TRAILER_KEY",
    "HEAD_CLOSED",
    "HEAD_NO_TRAILERS",
    "HEAD_OPEN_RED",
    "REASON_CLOSED_HEAD",
    "REASON_OPEN_RED",
    "REASON_STUB_CARVEOUT",
    "REASON_STUB_WITHOUT_PENDING_TEST",
    "REASON_TRAILER_FREE_HEAD",
    "RED_TRAILER_KEY",
    "REFUSE",
    "Decision",
    "decide",
    "head_state",
    "is_product_path",
    "refusal_message",
    "relative_path",
]

HEAD_OPEN_RED = "open-red"
HEAD_CLOSED = "closed"
HEAD_NO_TRAILERS = "no-trailers"

ALLOW = "allow"
REFUSE = "refuse"

REASON_OPEN_RED = "open-red"
REASON_STUB_CARVEOUT = "new-module-stub-carveout"
REASON_CLOSED_HEAD = "closed-head"
REASON_TRAILER_FREE_HEAD = "trailer-free-head"
REASON_STUB_WITHOUT_PENDING_TEST = "stub-without-pending-test"

RED_TRAILER_KEY = "TDD-Red-Test-File-Checksum:"
GREEN_TRAILER_KEY = "TDD-Green-Verified-At:"

_TESTS_PREFIX = "tests/"
_PYTHON_SUFFIX = ".py"


@dataclass(frozen=True, kw_only=True)
class Decision:
    """One allow-or-refuse verdict over one write target."""

    decision: str
    reason: str
    head_state: str
    path: str
    tool: str


def head_state(*, message: str) -> str:
    """Classify HEAD's commit message as open-red, closed, or trailer-free.

    An EMPTY message — the fail-closed value the guard substitutes when it
    cannot read HEAD at all — classifies as `no-trailers`, which refuses a
    product write rather than admitting one on an unreadable repository.
    """
    if RED_TRAILER_KEY not in message:
        return HEAD_NO_TRAILERS
    if GREEN_TRAILER_KEY in message:
        return HEAD_CLOSED
    return HEAD_OPEN_RED


def relative_path(*, path: str, repo_root: str) -> str:
    """Normalize a tool-supplied path to a repo-root-relative POSIX path.

    A path outside `repo_root` is returned unchanged, so it fails the
    declared-prefix test in `is_product_path` rather than being folded into
    the repository by a `..`-bearing relative form.
    """
    candidate = PurePosixPath(path)
    root = PurePosixPath(repo_root)
    if candidate.is_absolute():
        if root in candidate.parents:
            return str(candidate.relative_to(root))
        return path
    parts = tuple(part for part in candidate.parts if part != ".")
    return str(PurePosixPath(*parts)) if parts else path


def is_product_path(*, path: str, prefixes: tuple[str, ...]) -> bool:
    """True iff `path` is first-party product implementation Python.

    The same three clauses `red_green_replay._classify_staged` applies to its
    impl bucket: a `.py` suffix, a declared source prefix, and not vendored.
    `tests/` is excluded explicitly because this repository declares no source
    prefix under it and a future one must not silently capture the tests tree.
    """
    return (
        path.endswith(_PYTHON_SUFFIX)
        and path.startswith(prefixes)
        and not path.startswith(_TESTS_PREFIX)
        and not is_vendored_path(rel_path=Path(path))
    )


def decide(
    *,
    tool: str,
    path: str,
    head_state: str,
    exists_at_head: bool,
    test_change_pending: bool,
) -> Decision:
    """Return the allow-or-refuse verdict for one product-path write.

    Callers apply this ONLY to a path `is_product_path` accepted, and the
    verdict is independent of WHICH write tool asked: a `Write`, an `Edit`, a
    `MultiEdit` and a parsed shell write target all reach the same answer,
    which is what makes the Bash leg a parity surface rather than a second
    policy.
    """
    verdict, reason = _verdict(
        head_state=head_state,
        exists_at_head=exists_at_head,
        test_change_pending=test_change_pending,
    )
    return Decision(
        decision=verdict,
        reason=reason,
        head_state=head_state,
        path=path,
        tool=tool,
    )


def _verdict(
    *, head_state: str, exists_at_head: bool, test_change_pending: bool
) -> tuple[str, str]:
    if head_state == HEAD_OPEN_RED:
        return ALLOW, REASON_OPEN_RED
    if not exists_at_head:
        # The ONE carveout: a module absent from HEAD may be created as a
        # failing stub while its test is being written. It is gated on that
        # pending test change precisely so it cannot license building a whole
        # item out of "stubs" before any Red exists.
        if test_change_pending:
            return ALLOW, REASON_STUB_CARVEOUT
        return REFUSE, REASON_STUB_WITHOUT_PENDING_TEST
    if head_state == HEAD_CLOSED:
        return REFUSE, REASON_CLOSED_HEAD
    return REFUSE, REASON_TRAILER_FREE_HEAD


def refusal_message(*, decision: Decision) -> str:
    """Render the operator-facing refusal naming the required Red state."""
    return (
        f"REFUSED by livespec_tdd_order_guard: {decision.tool} may not write the product "
        f"path `{decision.path}` right now.\n\n"
        f"Reason: {decision.reason}. HEAD state: {decision.head_state}.\n\n"
        "An existing product file is writable only while HEAD is an open Red — a commit "
        f"whose message carries `{RED_TRAILER_KEY}` and does NOT yet carry "
        f"`{GREEN_TRAILER_KEY}`. Write the failing test for ONE acceptance assertion "
        "first, Red-commit that test alone, and then write the minimum implementation "
        "and Green-amend it.\n\n"
        "The ONE carveout is a new-module failing stub: a path that does not exist at "
        "HEAD may be created while a test change is uncommitted. Modifying a file that "
        "exists at HEAD is never part of that carveout.\n\n"
        "This refusal is deterministic, not a transient failure. Do NOT retry the same "
        "write; author the Red commit, or stop and ask the user."
    )
