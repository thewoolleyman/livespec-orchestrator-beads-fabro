"""Retain one complete released payload for a launcher invocation's lifetime.

A natively installed plugin runs out of a HARNESS-MANAGED cache directory,
and the harness is free to delete that directory the moment it installs a
newer build — while a dispatch launched from it is still running. Measured on
this host (work-item `bd-ib-mtuqxb`): PID 1894716 was still executing cache
`0.173.0`'s `scripts/bin/drive.py` after only `0.173.3` remained on disk.
`bd-ib-3ftj` records what that costs when the process finally reaches a module
it has not imported yet — a `_dispatcher_cost_wave` `ModuleNotFoundError`
hours into a run, with the same shape for any packaged asset read or
`scripts/bin/` helper spawn.

So the launcher copies the release ASIDE before any application import, and
runs the invocation from that copy. The copy is a plain whole-tree copy on
purpose: Python modules, the vendored dependency tree, the `.fabro` workflow
and prompt assets and the `bin/` helper wrappers all have to stay TOGETHER,
because each of the three failure modes above resolves its own path out of the
same root.

A plugin root that sits inside its own SOURCE REPOSITORY is NOT retained.
That tree belongs to an operator, not to the harness, so nothing evicts it —
and `_dispatcher_staleness_gate` already draws this line, exempting a
checkout plugin root from every currency question on the same ground. Keeping
the checkout case byte-for-byte unchanged also keeps this module out of the
path of every in-repo test and every hand-run CLI.

The derivation is the repository's own build files one level above the plugin
root, NOT a `.git` ancestor walk. A `.git` anywhere above the install flips
the answer, and "anywhere above" reaches places that have nothing to do with
this plugin: a dotfiles repository at `$HOME` sits above every per-user
plugin cache, and pytest's own session directory carried one on the host this
was measured on. Either would have silently disabled retention — the failure
direction that re-opens the bug — while reporting nothing.

Stdlib only, and no `livespec_orchestrator_beads_fabro` or `livespec_runtime`
import: this runs BEFORE `bootstrap()` puts either tree on `sys.path`, and
importing the packaged code to decide where the packaged code lives would
defeat the whole point.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "RetainedPayload",
    "harness_managed",
    "retain_payload",
]

# The published payload's directory name, and the name of the staging holder a
# copy lands in before it is published. Both are prefixed so an operator
# reading `/tmp` can tell what owns them.
_PAYLOAD_PREFIX = "livespec-orchestrator-beads-fabro-payload-"
_STAGING_PREFIX = "livespec-orchestrator-beads-fabro-staging-"
_STAGED_NAME = "payload"
# The release identity a payload is keyed by, read from the released plugin
# manifest. `_UNKNOWN_RELEASE` keeps an unreadable or malformed manifest on the
# retention path rather than refusing: a payload under a vaguer key is still a
# payload that survives eviction, and refusing here would turn a cosmetic
# manifest fault into a dead launcher.
_RELEASE_MANIFEST = "plugin.json"
_RELEASE_KEY = "version"
_UNKNOWN_RELEASE = "unknown-release"
# What marks the tree one level above the plugin root as this plugin's own
# source repository rather than a cache directory that merely contains an
# install. Both are files the repository builds with and a released payload
# never ships.
_SOURCE_REPOSITORY_MARKERS = ("pyproject.toml", "justfile")
# Byte-compiled caches are reproducible from the sources beside them, so they
# are the one thing the copy leaves behind.
_IGNORED_NAMES = ("__pycache__",)


@dataclass(frozen=True, kw_only=True)
class RetainedPayload:
    """Where one invocation reads its code and its packaged assets from.

    `retained` is False when the source tree IS the payload — the
    source-repository case, where nothing was copied and nothing about the
    invocation changes.
    """

    root: Path
    scripts_root: Path
    vendor_root: Path
    retained: bool


def retain_payload(*, source_root: Path) -> RetainedPayload:
    """Resolve the payload this invocation should run from, copying it if needed."""
    if not harness_managed(source_root=source_root):
        return _payload_at(root=source_root, retained=False)
    return _payload_at(root=_retained_root(source_root=source_root), retained=True)


def harness_managed(*, source_root: Path) -> bool:
    """Whether this plugin root is a harness-managed install rather than a checkout.

    PUBLIC because the answer is the whole precondition for retention, and a
    caller deciding whether to expect a retained payload needs to ask the same
    question the same way. ANY repository marker above the root is enough to
    answer "checkout": an unnecessary retention would relocate a developer's
    own tree, so the ambiguous case declines rather than acts.
    """
    return not any((source_root.parent / marker).exists() for marker in _SOURCE_REPOSITORY_MARKERS)


def _payload_at(*, root: Path, retained: bool) -> RetainedPayload:
    scripts_root = root / "scripts"
    return RetainedPayload(
        root=root,
        scripts_root=scripts_root,
        vendor_root=scripts_root / "_vendor",
        retained=retained,
    )


def _retained_root(*, source_root: Path) -> Path:
    """The retained payload for this release, copying it aside on first demand."""
    release = _release_identity(source_root=source_root)
    root = Path(tempfile.gettempdir()) / f"{_PAYLOAD_PREFIX}{release}"
    if root.is_dir():
        return root
    return _published(source_root=source_root, root=root)


def _published(*, source_root: Path, root: Path) -> Path:
    """Copy the release into a staging holder, then publish it with one rename.

    The copy is never built UNDER its published name: a half-written tree
    there would be adopted as a payload by the next invocation, which is the
    one outcome worse than no payload at all. A rename that loses the race to
    a concurrent invocation discards its own staging and takes the published
    tree, so two invocations never both publish.
    """
    holder = Path(tempfile.mkdtemp(prefix=_STAGING_PREFIX))
    staged = holder / _STAGED_NAME
    _ = shutil.copytree(source_root, staged, ignore=shutil.ignore_patterns(*_IGNORED_NAMES))
    try:
        _ = staged.rename(root)
    except OSError:
        shutil.rmtree(holder, ignore_errors=True)
        return root
    holder.rmdir()
    return root


def _release_identity(*, source_root: Path) -> str:
    """The released version this payload carries, or `_UNKNOWN_RELEASE`."""
    try:
        text = (source_root / _RELEASE_MANIFEST).read_text(encoding="utf-8")
    except OSError:
        return _UNKNOWN_RELEASE
    try:
        parsed = json.loads(text)
    except ValueError:
        return _UNKNOWN_RELEASE
    if not isinstance(parsed, dict):
        return _UNKNOWN_RELEASE
    version = cast("dict[str, object]", parsed).get(_RELEASE_KEY)
    if not isinstance(version, str) or not version.strip():
        return _UNKNOWN_RELEASE
    return version.strip()
