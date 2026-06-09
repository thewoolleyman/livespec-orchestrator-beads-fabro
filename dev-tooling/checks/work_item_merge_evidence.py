# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""work_item_merge_evidence — beads-private merge-evidence static check.

Ports the spec'd `work_item_merge_evidence` static check
(SPECIFICATION/contracts.md §"`work_item_merge_evidence` static check")
onto the beads substrate. Where the plaintext sibling walks JSONL records,
this walks every materialized work-item from the configured store
descriptor — reading the `AuditRecord` from each closed issue's `metadata`
column through the same beads client the runtime uses. In hermetic mode
(`LIVESPEC_BEADS_FAKE` truthy, the default `just check` tier) the tenant is
empty, so the walk yields nothing and the check passes trivially.

Rules, for each work-item with `status == "closed"`:

- resolution in {completed, spec-revised, resolved-out-of-band}: REQUIRE a
  non-null `AuditRecord`, REQUIRE non-empty `merge_sha`, REQUIRE
  `git cat-file -e <merge_sha>` exits 0 (the SHA exists locally), and
  REQUIRE `git merge-base --is-ancestor <merge_sha> origin/<canonical_branch>`
  exits 0 (the SHA is reachable from the canonical branch tip).
- resolution in {wontfix, duplicate, no-longer-applicable}: REQUIRE NO
  `AuditRecord` is present (the negative-evidence case — an administratively
  closed record must not carry merge-evidence).
- resolution is null with status closed: FAIL ("closed work-item without
  resolution is malformed").

Work-items with `type == "epic"` are EXEMPT from the merge-evidence
requirement; the check INSTEAD requires every beads parent-child child of
the epic to resolve to a closed work-item.

All git operations are local (`cat-file`, `merge-base`); the check performs
no network I/O. The `canonical_branch` is read from `.livespec.jsonc`'s
plugin block (default `master`). Per-violation diagnostics flow through
structlog (JSON to stderr) — the only output surface the `no_write_direct`
ban permits for an enforcement script; structlog is imported from the
installed `livespec_dev_tooling` package's vendored copy (it is not vendored
in this repo's own tree). The exit code (0 pass / 1 fail) is the load-bearing
signal the `just` target propagates to the shell.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
_SCRIPTS_VENDOR = _SCRIPTS / "_vendor"
for _path in (_SCRIPTS, _SCRIPTS_VENDOR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script
# (per the `no_write_direct` ban on direct `sys.stderr.write`). It is not
# vendored in this repo's own tree, so it is imported from the installed
# `livespec_dev_tooling` package's vendored copy, whose path is added to
# `sys.path` here. The file-level pyright pragma above silences the
# untyped-structlog diagnostics this import would otherwise raise.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
if str(_DT_VENDOR) not in sys.path:
    sys.path.insert(0, str(_DT_VENDOR))

import structlog  # noqa: E402
from livespec_impl_beads.commands import _jsonc  # noqa: E402
from livespec_impl_beads.commands._config import resolve_store_config  # noqa: E402
from livespec_impl_beads.store import (  # noqa: E402
    materialize_work_items,
    read_work_items,
)
from livespec_impl_beads.types import WorkItem  # noqa: E402

__all__: list[str] = ["main"]

_REQUIRE_EVIDENCE_RESOLUTIONS = frozenset({"completed", "spec-revised", "resolved-out-of-band"})
_NEGATIVE_EVIDENCE_RESOLUTIONS = frozenset({"wontfix", "duplicate", "no-longer-applicable"})

_DEFAULT_CANONICAL_BRANCH = "master"
_LIVESPEC_CONFIG = ".livespec.jsonc"
_PLUGIN_BLOCK = "livespec-impl-beads"
_CANONICAL_BRANCH_KEY = "canonical_branch"


def _resolve_canonical_branch(*, cwd: Path) -> str:
    """Read `canonical_branch` from the plugin's `.livespec.jsonc` block."""
    config_path = cwd / _LIVESPEC_CONFIG
    if not config_path.is_file():
        return _DEFAULT_CANONICAL_BRANCH
    try:
        parsed = _jsonc.loads(text=config_path.read_text(encoding="utf-8"))
    except _jsonc.JsoncParseError:
        return _DEFAULT_CANONICAL_BRANCH
    if not isinstance(parsed, dict):
        return _DEFAULT_CANONICAL_BRANCH
    parsed_dict = cast("dict[str, Any]", parsed)
    block = parsed_dict.get(_PLUGIN_BLOCK)
    if not isinstance(block, dict):
        return _DEFAULT_CANONICAL_BRANCH
    block_dict = cast("dict[str, Any]", block)
    value = block_dict.get(_CANONICAL_BRANCH_KEY)
    if isinstance(value, str) and value != "":
        return value
    return _DEFAULT_CANONICAL_BRANCH


def _git_ok(*, cwd: Path, args: list[str]) -> bool:
    """Run a local git command; return True iff it exits 0 (network-free)."""
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _sha_reachable(*, cwd: Path, merge_sha: str, canonical_branch: str) -> bool:
    """The SHA exists locally AND is an ancestor of origin/<canonical_branch>."""
    if not _git_ok(cwd=cwd, args=["cat-file", "-e", merge_sha]):
        return False
    return _git_ok(
        cwd=cwd,
        args=["merge-base", "--is-ancestor", merge_sha, f"origin/{canonical_branch}"],
    )


def _evidence_violation(
    *,
    cwd: Path,
    item: WorkItem,
    canonical_branch: str,
) -> str | None:
    """Return a violation message for a positive-evidence closure, or None."""
    if item.audit is None:
        return "closed/completed work-item missing required audit merge-evidence"
    if item.audit.merge_sha == "":
        return "audit.merge_sha is empty for a completed closure"
    if not _sha_reachable(
        cwd=cwd, merge_sha=item.audit.merge_sha, canonical_branch=canonical_branch
    ):
        return (
            f"audit.merge_sha {item.audit.merge_sha!r} is not reachable from "
            f"origin/{canonical_branch}"
        )
    return None


def _negative_evidence_violation(*, item: WorkItem) -> str | None:
    """An administratively closed record MUST NOT carry merge-evidence."""
    if item.audit is not None:
        return "administratively closed work-item must not carry an audit record"
    return None


def _local_child_id(*, entry: object) -> str | None:
    """Extract the local child id from a `depends_on` entry, or None.

    Mirrors the store's `_local_depends_on_id`: accepts both the legacy
    bare-string form and the v072 typed-dict local form
    `{"kind":"local","work_item_id":<id>}`. Non-local kinds have no
    in-tenant child to resolve and yield None.
    """
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        typed = cast("dict[str, Any]", entry)
        if typed.get("kind") == "local":
            work_item_id = typed.get("work_item_id")
            if isinstance(work_item_id, str):
                return work_item_id
    return None


def _epic_violation(*, item: WorkItem, index: dict[str, WorkItem]) -> str | None:
    """Every child of a closed epic MUST itself resolve to a closed work-item."""
    for entry in item.depends_on:
        child_id = _local_child_id(entry=entry)
        if child_id is None:
            continue
        child = index.get(child_id)
        if child is not None and child.status != "closed":
            return f"closed epic has non-closed child {child_id!r}"
    return None


def _item_violation(
    *,
    cwd: Path,
    item: WorkItem,
    index: dict[str, WorkItem],
    canonical_branch: str,
) -> str | None:
    """Apply the merge-evidence rules to one closed work-item."""
    if item.type == "epic":
        return _epic_violation(item=item, index=index)
    if item.resolution is None:
        return "closed work-item without resolution is malformed"
    if item.resolution in _REQUIRE_EVIDENCE_RESOLUTIONS:
        return _evidence_violation(cwd=cwd, item=item, canonical_branch=canonical_branch)
    if item.resolution in _NEGATIVE_EVIDENCE_RESOLUTIONS:
        return _negative_evidence_violation(item=item)
    return None


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("work_item_merge_evidence")
    cwd = Path.cwd()
    canonical_branch = _resolve_canonical_branch(cwd=cwd)
    config = resolve_store_config(cwd=cwd, work_items_arg=None, memos_arg=None)
    index = materialize_work_items(read_work_items(path=config.work_items_path))
    violations: list[tuple[str, str]] = []
    for item in index.values():
        if item.status != "closed":
            continue
        message = _item_violation(
            cwd=cwd, item=item, index=index, canonical_branch=canonical_branch
        )
        if message is not None:
            violations.append((item.id, message))
    if not violations:
        return 0
    for work_item_id, message in violations:
        log.error("work-item merge-evidence violation", work_item=work_item_id, detail=message)
    return 1


# The shebang-less module is invoked via `just check-work-item-merge-evidence`
# (`uv run python dev-tooling/checks/work_item_merge_evidence.py`); the guard
# keeps the exit code propagating to the shell.
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
