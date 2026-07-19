"""SessionStart codex-YOLO re-apply hook — force danger-full-access, warn on drift.

Forces the openai-codex plugin's Codex threads to `danger-full-access` ("YOLO":
full disk + network, no OS sandbox), so plugin-driven Codex rescues AND reviews
can actually execute (pytest / git / gh) instead of silently passing code they
could never run.

WHY self-carried: openai/codex-plugin-cc hardcodes a restrictive sandbox on every
plugin-launched thread — `buildThreadParams` / `buildResumeParams` default to
`read-only`, and the review / adversarial-review / task sites pin
read-only / workspace-write. None of those enable network. Upstream offers no
toggle: every configurable-sandbox issue/PR is unmerged or author-withdrawn (see
`plan/codex-yolo-sandbox/research.md`). A plugin refresh clobbers the cache, so
this hook re-applies the patch every session, registered in `.claude/settings.json`
under `hooks.SessionStart` AFTER `just ensure-plugins`.

WHAT: rewrites the single sandbox chokepoint in every cached plugin version,
`STOCK` -> `PATCHED`. `buildThreadParams` / `buildResumeParams` are the ONLY two
thread-param builders and every plugin path (task, review, adversarial-review,
resume) flows through them, so this one line in `lib/codex.mjs` covers all of
them. `CODEX_COMPANION_SANDBOX` is an escape-hatch: set it (e.g. to `read-only`
or `workspace-write`) to downgrade a single run.

THE DRIFT CANARY: the hook's worst failure is silent. If OpenAI restructures
`codex.mjs` so the stock chokepoint string no longer matches, the rewrite becomes
a no-op and Codex quietly reverts to read-only — a reviewer that cannot execute
passing code it never ran. `classify_state` therefore distinguishes a file that
carries NEITHER the stock string NOR our sentinel (`drift`) from one already
patched (`patched`), and `main` writes a loud stderr WARNING for every drifted
file.

Idempotent: only the stock chokepoint is rewritten, so a second run is a no-op.
Fail-open throughout: an absent plugin cache or an unreadable file is a silent
pass-through (exit 0), never an error — a session must never fail to start
because the Codex plugin is missing.

The classification and rewrite logic is PURE so it is unit-testable by import,
with no subprocess spawn (`check-tests-no-subprocess-spawn`); the paired
`codex-yolo-reapply.sh` is a thin wrapper, mirroring `beads_access_guard.py` +
`beads-access-guard.sh`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

__all__: list[str] = [
    "CACHE_GLOB",
    "PATCHED",
    "SENTINEL",
    "STOCK",
    "apply_patch",
    "cached_codex_mjs_paths",
    "classify_state",
    "main",
    "read_text_or_none",
]

STOCK: str = 'sandbox: options.sandbox ?? "read-only"'
PATCHED: str = 'sandbox: process.env.CODEX_COMPANION_SANDBOX || "danger-full-access"'

# The escape-hatch env var also serves as the patch sentinel: its presence is how
# an already-patched file is told apart from an upstream-restructured one.
SENTINEL: str = "CODEX_COMPANION_SANDBOX"

# Home-relative; every cached plugin VERSION is patched, not just the newest, so
# a rollback to an older cached version stays full-access.
CACHE_GLOB: str = ".claude/plugins/cache/openai-codex/codex/*/scripts/lib/codex.mjs"

State = Literal["stock", "patched", "drift", "absent"]

_DRIFT_WARNING: str = (
    "[codex-yolo-reapply] WARNING: sandbox chokepoint DRIFT in {path} — the file "
    "carries neither the stock read-only default nor our CODEX_COMPANION_SANDBOX "
    "sentinel. The codex plugin was almost certainly restructured upstream, so "
    "Codex threads are running with an UNKNOWN sandbox and may have silently "
    "reverted to read-only (no network, so no pytest / gh — a reviewer that "
    "cannot execute passes code it never ran). Re-derive the chokepoint strings "
    "in .claude/hooks/codex_yolo_reapply.py; see plan/codex-yolo-sandbox/."
)

_APPLIED: str = "[codex-yolo-reapply] forced danger-full-access in {path}"


def classify_state(*, content: str | None) -> State:
    """Classify a cached `codex.mjs` by which sandbox chokepoint it carries.

    `absent` — `content` is None: the file does not exist or could not be read.
    `stock`  — the upstream read-only default is present and needs rewriting.
    `patched`— our `CODEX_COMPANION_SANDBOX` sentinel is present; nothing to do.
    `drift`  — neither marker is present; the chokepoint moved upstream and this
               hook has silently stopped working. That is the canary state.
    """
    if content is None:
        return "absent"
    if STOCK in content:
        return "stock"
    if SENTINEL in content:
        return "patched"
    return "drift"


def apply_patch(*, content: str) -> str:
    """Return `content` with every stock chokepoint rewritten to full access."""
    return content.replace(STOCK, PATCHED)


def read_text_or_none(*, path: Path) -> str | None:
    """Return the UTF-8 text of `path`, or None when it cannot be read.

    Fail-open seam: a glob match that is a directory, a dangling link, or a
    permission-denied file classifies as `absent` rather than raising.
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def cached_codex_mjs_paths(*, home: Path) -> list[Path]:
    """Return every cached openai-codex `lib/codex.mjs` under `home`, sorted."""
    return sorted(home.glob(CACHE_GLOB))


def main() -> int:
    """Re-apply the full-access patch to every cached codex.mjs; warn on drift.

    Always exits 0 (fail-open): an absent plugin cache yields no paths and no
    output, and an unreadable match is skipped.
    """
    for path in cached_codex_mjs_paths(home=Path.home()):
        _reconcile(path=path)
    return 0


def _reconcile(*, path: Path) -> None:
    """Patch, warn, or leave alone a single cached `codex.mjs`."""
    content = read_text_or_none(path=path)
    state = classify_state(content=content)
    if state == "drift":
        print(_DRIFT_WARNING.format(path=path), file=sys.stderr)
        return
    # `content is None` is the `absent` state; the second test then leaves a
    # `patched` file alone. Only `stock` falls through to the rewrite.
    if content is None or state != "stock":
        return
    _ = path.write_text(apply_patch(content=content), encoding="utf-8")
    print(_APPLIED.format(path=path))


if __name__ == "__main__":
    raise SystemExit(main())
