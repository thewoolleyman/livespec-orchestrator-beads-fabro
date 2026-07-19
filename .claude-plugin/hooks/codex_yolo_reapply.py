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
this hook re-applies the patch every session through the plugin-bundled
`hooks/hooks.json` SessionStart registration.

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
carries NEITHER the stock string NOR our exact `PATCHED` rewrite (`drift`) from
one already patched, and `main` writes a loud stderr WARNING for every drifted
file. The `patched` test matches the FULL rewrite rather than the bare env-var
name, so an upstream file that merely MENTIONS `CODEX_COMPANION_SANDBOX` cannot
masquerade as patched and silence the canary.

Idempotent: only the stock chokepoint is rewritten, so a second run is a no-op.
Fail-open throughout: an absent plugin cache or an unreadable file is a silent
pass-through (exit 0), never an error — a session must never fail to start
because the Codex plugin is missing.

The classification and rewrite logic is PURE so it is unit-testable by import,
with no subprocess spawn (`check-tests-no-subprocess-spawn`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import codex_yolo_gate

__all__: list[str] = [
    "CACHE_GLOB",
    "PATCHED",
    "STOCK",
    "apply_patch",
    "cached_codex_mjs_paths",
    "classify_state",
    "main",
    "read_text_or_none",
    "write_text_or_false",
]

STOCK: str = 'sandbox: options.sandbox ?? "read-only"'

# `PATCHED` is BOTH the rewrite and the patch sentinel: "already patched" means
# this EXACT expression is present, nothing looser.
#
# It used to be enough for the bare env-var name `CODEX_COMPANION_SANDBOX` to
# appear anywhere in the file, which defeated the canary in exactly the scenario
# the canary exists for. If upstream restructures the chokepoint (so `STOCK` no
# longer matches) AND the file mentions that name anywhere — a comment, a doc
# line, or most plausibly upstream landing its OWN toggle, since the unmerged
# upstream proposal is literally named `CODEX_COMPANION_SANDBOX_MODE` and
# CONTAINS our name as a substring — then an unpatched file classified as
# `patched`. Silent, no warning, Codex quietly back on read-only.
#
# Matching the full expression fails in the safe direction instead: a cosmetic
# upstream reformat of our own line now reports `drift`, which is merely loud.
PATCHED: str = 'sandbox: process.env.CODEX_COMPANION_SANDBOX || "danger-full-access"'

# Home-relative; every cached plugin VERSION is patched, not just the newest, so
# a rollback to an older cached version stays full-access.
CACHE_GLOB: str = ".claude/plugins/cache/openai-codex/codex/*/scripts/lib/codex.mjs"

State = Literal["stock", "patched", "drift", "absent"]

_DRIFT_WARNING: str = (
    "[codex-yolo-reapply] WARNING: sandbox chokepoint DRIFT in {path} — the file "
    "carries neither the stock read-only default nor our exact full-access "
    "rewrite. The codex plugin was almost certainly restructured upstream, so "
    "Codex threads are running with an UNKNOWN sandbox and may have silently "
    "reverted to read-only (no network, so no pytest / gh — a reviewer that "
    "cannot execute passes code it never ran). Re-derive the chokepoint strings "
    "in .claude-plugin/hooks/codex_yolo_reapply.py; see plan/codex-yolo-sandbox/."
)

_APPLIED: str = "[codex-yolo-reapply] forced danger-full-access in {path}"

_SKIPPED: str = (
    "[codex-yolo-reapply] WARNING: skipped {path} — it could not be read or rewritten. "
    "That cached plugin version is still on the stock read-only sandbox, so Codex threads "
    "resolved from it cannot reach the network (no pytest / gh). Other cached versions were "
    "still processed."
)


def classify_state(*, content: str | None) -> State:
    """Classify a cached `codex.mjs` by which sandbox chokepoint it carries.

    `absent` — `content` is None: the file does not exist or could not be read.
    `stock`  — the upstream read-only default is present and needs rewriting.
    `patched`— our exact `PATCHED` rewrite is present; nothing to do.
    `drift`  — neither marker is present; the chokepoint moved upstream and this
               hook has silently stopped working. That is the canary state.
    """
    if content is None:
        return "absent"
    if STOCK in content:
        return "stock"
    if PATCHED in content:
        return "patched"
    return "drift"


def apply_patch(*, content: str) -> str:
    """Return `content` with every stock chokepoint rewritten to full access."""
    return content.replace(STOCK, PATCHED)


def read_text_or_none(*, path: Path) -> str | None:
    """Return the UTF-8 text of `path`, or None when it cannot be read.

    Fail-open seam: a glob match that is a directory, a dangling link, or a
    permission-denied file classifies as `absent` rather than raising.

    `UnicodeDecodeError` is caught alongside `OSError` because it is NOT an
    `OSError` (it derives from `ValueError`), so an `except OSError` alone lets
    a non-UTF-8 `codex.mjs` escape as a traceback and take the whole
    SessionStart hook down with it. The shell implementation this module
    replaced survived that case — the decode error was confined to a `python3
    -c` subprocess whose non-zero exit the loop ignored — so letting it
    propagate here would be a regression, not merely a gap.
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def write_text_or_false(*, path: Path, content: str) -> bool:
    """Write `content` to `path`; return False when the write is refused.

    The other half of the fail-open seam. A cached `codex.mjs` can be readable
    but not writable (a read-only plugin cache, a root-owned file, a full
    disk), and an unguarded `write_text` would raise straight out of the
    SessionStart hook. The shell implementation degraded the same case to "skip
    this file, keep going, exit 0"; so does this.
    """
    try:
        _ = path.write_text(content, encoding="utf-8")
    except OSError:
        return False
    return True


def cached_codex_mjs_paths(*, home: Path) -> list[Path]:
    """Return every cached openai-codex `lib/codex.mjs` under `home`, sorted."""
    return sorted(home.glob(CACHE_GLOB))


def main() -> int:
    """Re-apply the full-access patch to every cached codex.mjs; warn on drift.

    Always exits 0 (fail-open): an absent plugin cache yields no paths and no
    output, and an unreadable match is skipped.
    """
    if codex_yolo_gate.gate_state() == "off":
        return 0
    for path in cached_codex_mjs_paths(home=Path.home()):
        _reconcile_guarded(path=path)
    return 0


def _reconcile_guarded(*, path: Path) -> None:
    """Per-file bulkhead: one bad file must never abort the remaining ones.

    The shell implementation got this isolation for free — each file was
    handled by its own `python3 -c` subprocess, so a failure there died with
    that subprocess and the loop moved on. Folding the loop into ONE process
    lost that property: an exception escaping any single file aborted `main`
    outright, so every alphabetically-later cached version silently stayed at
    the stock `read-only` chokepoint. That is worse than the failure the drift
    canary exists to catch, because it emits no warning at all.

    So the isolation is restored explicitly. The catch is deliberately broad:
    the specific failures are already handled precisely in `read_text_or_none`
    and `write_text_or_false`, and this is the last-resort net for the ones not
    yet imagined. A SessionStart hook that raises is a hook that can wedge the
    session — matching `livespec_footgun_guard.py`, which takes the same
    fail-open posture for the same reason.
    """
    try:
        _reconcile(path=path)
    except Exception:  # noqa: BLE001 — deliberate fail-open bulkhead; see docstring.
        print(_SKIPPED.format(path=path), file=sys.stderr)


def _reconcile(*, path: Path) -> None:
    """Patch, warn, or leave alone a single cached `codex.mjs`."""
    content = read_text_or_none(path=path)
    if content is None:
        return
    state = classify_state(content=content)
    if state == "drift":
        print(_DRIFT_WARNING.format(path=path), file=sys.stderr)
        return
    if state == "patched":
        return
    # Report only what actually landed: a refused write leaves the file stock,
    # so claiming "forced danger-full-access" would be a lie the operator acts on.
    if write_text_or_false(path=path, content=apply_patch(content=content)):
        print(_APPLIED.format(path=path))


if __name__ == "__main__":
    raise SystemExit(main())
