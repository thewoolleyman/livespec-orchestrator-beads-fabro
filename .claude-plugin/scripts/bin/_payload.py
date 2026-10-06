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

# The invocation-private holder's directory-name prefix, and the fixed name the
# payload takes inside it. The prefix is there so an operator reading `/tmp`
# can tell what owns the directory; the holder's UNIQUE suffix comes from
# `mkdtemp`, never from anything about the release.
_PAYLOAD_PREFIX = "livespec-orchestrator-beads-fabro-payload-"
_STAGED_NAME = "payload"
# The release this payload carries, read from the released plugin manifest and
# used ONLY to label the holder directory for a human reader.
# `_UNKNOWN_RELEASE` keeps an unreadable or malformed manifest on the retention
# path rather than refusing: a payload under a vaguer LABEL is still a payload
# that survives eviction, and refusing here would turn a cosmetic manifest
# fault into a dead launcher.
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
    """Copy the release into a directory THIS invocation alone owns.

    The holder comes from `mkdtemp`, so it is created fresh, mode 0700, by
    this process — which is what makes adoption structurally impossible. An
    earlier invocation's tree, a symlink planted at a guessable path, a
    foreign-owned directory, a half-copied tree left by an interrupted
    provision: none of them is ever CONSULTED, because no existing path is.

    A shared payload keyed by release identity was tried and is wrong. Two
    installs can carry the same `plugin.json` version and be different trees —
    a cache rebuilt at the same release, a locally-installed marketplace copy,
    a release re-cut from another commit — so version TEXT is not content
    provenance, and adopting on a version match made one invocation execute
    another source's code with nothing to report the substitution. The release
    goes into the directory NAME for an operator reading `/tmp`, and carries
    no identity weight at all.
    """
    release = _release_identity(source_root=source_root)
    holder = Path(tempfile.mkdtemp(prefix=f"{_PAYLOAD_PREFIX}{release}-"))
    root = holder / _STAGED_NAME
    _ = shutil.copytree(source_root, root, ignore=shutil.ignore_patterns(*_IGNORED_NAMES))
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
