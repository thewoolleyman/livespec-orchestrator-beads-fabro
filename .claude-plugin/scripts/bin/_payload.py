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
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "PAYLOAD_ROOT_ENV",
    "PayloadRefusal",
    "RetainedPayload",
    "harness_managed",
    "missing_payload_paths",
    "payload_fidelity_gaps",
    "payload_relative_argv",
    "release_payload",
    "retain_payload",
]

# How an invocation hands its payload down to the children it spawns. One
# dispatch is several processes — `drive`, the `dispatcher.py` it starts, the
# helpers that starts in turn — and they must all read the SAME tree, so a
# child that finds this set and pointing at a complete payload REUSES it
# instead of copying the copy.
PAYLOAD_ROOT_ENV = "LIVESPEC_RETAINED_PAYLOAD_ROOT"

# The invocation-private holder's directory-name prefix, and the fixed name the
# payload takes inside it. The prefix is there so an operator reading `/tmp`
# can tell what owns the directory; the holder's UNIQUE suffix comes from
# `mkdtemp`, never from anything about the release.
_PAYLOAD_PREFIX = "livespec-orchestrator-beads-fabro-payload-"
_STAGED_NAME = "payload"
# The release this payload carries, read from the released plugin manifest.
# It labels the holder directory for a human reader, but it is NOT only a
# label: it is the payload's PROVENANCE, and provenance is what every
# downstream build comparison is made of — the minimum-release floor, the
# self-update canary and the registered-install currency finding all compare
# one build's release against another's. So an unusable manifest REFUSES.
#
# This degraded to the placeholder string `unknown-release` and carried on,
# which was the wrong direction: a payload whose own release cannot be
# established cannot be compared with anything, and a placeholder leaves
# "which build is this" unanswerable while every surface that asks keeps
# reporting an answer. It also made two such payloads indistinguishable in the
# one place an operator reads these directories by eye.
_RELEASE_MANIFEST = "plugin.json"
_RELEASE_KEY = "version"
# What marks the tree one level above the plugin root as this plugin's own
# source repository rather than a cache directory that merely contains an
# install. Both are files the repository builds with and a released payload
# never ships.
_SOURCE_REPOSITORY_MARKERS = ("pyproject.toml", "justfile")
# Byte-compiled caches are reproducible from the sources beside them, so they
# are the one thing the copy leaves behind.
_IGNORED_NAMES = ("__pycache__",)
# How many differing paths a fidelity refusal names. An operator needs enough
# to recognise WHAT is missing, not the whole set.
_FIDELITY_REPORT_LIMIT = 5
# What this launcher needs for a payload to be usable at all, split by TYPE
# because `exists()` is blind to it: a directory satisfies `exists()` where a
# module is needed, and a plain file satisfies it where a tree is needed.
#
# Deliberately NOT read from `cache-manifest.json`. That manifest serves the
# fleet's `ensure-plugins` verification and omits `scripts/_vendor` and
# `.fabro/` entirely — the two trees whose absence produced the measured
# `ModuleNotFoundError`. A completeness contract that cannot see the thing that
# broke is not the contract to validate against.
_REQUIRED_FILES: tuple[tuple[str, ...], ...] = (
    ("plugin.json",),
    ("scripts", "bin", "_bootstrap.py"),
    ("scripts", "bin", "_payload.py"),
    ("scripts", "livespec_orchestrator_beads_fabro", "__init__.py"),
)
# Required trees, which must also be NON-EMPTY. An empty `_vendor` fails every
# deferred `livespec_runtime` import and an empty `workflows` fails every
# packaged asset read — both at the far end of a dispatch, which is the
# failure retention exists to prevent, so neither may be published.
_REQUIRED_TREES: tuple[tuple[str, ...], ...] = (
    ("scripts", "_vendor"),
    ("scripts", "livespec_orchestrator_beads_fabro", "commands"),
    (".fabro", "workflows"),
)


@dataclass(frozen=True, kw_only=True)
class RetainedPayload:
    """Where one invocation reads its code and its packaged assets from.

    `retained` is False when the source tree IS the payload — the
    source-repository case, where nothing was copied and nothing about the
    invocation changes.

    `holder` is the private directory THIS process created and is therefore
    responsible for removing, and it is `None` for every payload this process
    did not create: a source-repository tree, and an INHERITED payload a
    parent invocation still owns. That is the whole ownership rule, and it is
    expressed as the absence of a path rather than as a flag, so a release
    has nothing to remove unless this process made it.
    """

    root: Path
    scripts_root: Path
    vendor_root: Path
    retained: bool
    holder: Path | None = None


@dataclass(frozen=True, kw_only=True)
class PayloadRefusal:
    """Why this invocation has no usable payload, phrased for an operator.

    Returned rather than raised: the caller is the pre-import launcher, and it
    owes the operator one actionable line and a precondition exit code — not a
    traceback through machinery that was never the problem.
    """

    message: str


def retain_payload(
    *, source_root: Path, environ: MutableMapping[str, str]
) -> RetainedPayload | PayloadRefusal:
    """Resolve the payload this invocation runs from, or refuse with a reason.

    A refusal here lands BEFORE any application import, so it lands before the
    Dispatcher can claim a work item or start a factory run. That ordering is
    the point: a dispatch that discovers its payload is unusable only after
    claiming has stranded the item, which is the same cost the retention
    exists to prevent, moved to a later moment.

    `environ` is both read and WRITTEN: an inherited payload is adopted from
    it, and a freshly provisioned one is published into it so this process's
    own children find it. It is a parameter rather than `os.environ` so the
    publication is visible to a caller instead of being a hidden global
    effect.
    """
    inherited = _inherited_payload(environ=environ)
    if inherited is not None:
        return inherited
    if not harness_managed(source_root=source_root):
        return _payload_at(root=source_root, retained=False)
    missing = missing_payload_paths(root=source_root)
    if missing:
        return PayloadRefusal(
            message=_incomplete_message(root=source_root, missing=missing, subject="installation")
        )
    retained = _retained_root(source_root=source_root)
    if isinstance(retained, PayloadRefusal):
        return retained
    environ[PAYLOAD_ROOT_ENV] = str(retained)
    return _payload_at(root=retained, retained=True, holder=retained.parent)


def release_payload(*, payload: RetainedPayload) -> None:
    """Remove the private payload this process created, if it created one.

    Called at normal interpreter exit, which is AFTER the invocation's own
    children have been waited on — `drive` runs its Dispatcher to completion
    and `dispatcher.py` runs its helpers to completion, both synchronously —
    so an owned consumer is never reading a tree this removes. A payload with
    no `holder` is one this process does not own, and nothing happens.

    `ignore_errors` because this runs during shutdown: a payload that cannot
    be fully removed is a disk-space problem for a later sweep, never a reason
    to turn a completed invocation into a failed one.
    """
    if payload.holder is None:
        return
    shutil.rmtree(payload.holder, ignore_errors=True)


def _inherited_payload(*, environ: MutableMapping[str, str]) -> RetainedPayload | None:
    """Adopt the payload a parent invocation published, when it is still complete.

    An incomplete or vanished inherited payload falls through to a fresh
    provision rather than refusing: the parent may have exited and cleaned up,
    and a child that can still provision for itself should. Nothing here is
    ADOPTED on trust — the same completeness contract a fresh copy must pass
    is applied before this tree is executed.
    """
    recorded = environ.get(PAYLOAD_ROOT_ENV, "")
    if not recorded:
        return None
    root = Path(recorded)
    if missing_payload_paths(root=root):
        return None
    return _payload_at(root=root, retained=True)


def missing_payload_paths(*, root: Path) -> tuple[str, ...]:
    """The required payload members `root` cannot supply, as POSIX relative paths.

    "Cannot supply" rather than "does not have": a required FILE that is a
    directory, and a required TREE that is a plain file or is empty, are all
    reported. Each was `exists()`-complete and unusable.
    """
    gaps = [
        "/".join(relative) for relative in _REQUIRED_FILES if not root.joinpath(*relative).is_file()
    ]
    gaps.extend(
        "/".join(relative)
        for relative in _REQUIRED_TREES
        if not _usable_tree(path=root.joinpath(*relative))
    )
    return tuple(gaps)


def _usable_tree(*, path: Path) -> bool:
    """Whether `path` is a directory that actually holds something."""
    if not path.is_dir():
        return False
    return any(path.iterdir())


def payload_fidelity_gaps(*, source_root: Path, payload_root: Path) -> tuple[str, ...]:
    """Files the SOURCE has that the payload does not, or holds at a different size.

    This is what makes the payload provably the SAME RELEASE rather than
    merely the right shape. No list of required paths can answer that: the
    incident module `_dispatcher_cost_wave.py` is one of hundreds no contract
    enumerates, and a copy missing exactly it satisfied every structural
    grade. Comparing the copy against the tree it was made from needs no
    manifest and no registry, and it catches a copy truncated by an eviction
    landing mid-provision.

    Size, not content hash: the realistic failure here is a file ABSENT or
    SHORT, which size settles, and byte-integrity of an extracted release is
    the fleet packaging concern tracked separately — not this launcher's.

    Returns at most `_FIDELITY_REPORT_LIMIT` paths. The whole set is not
    useful in a refusal an operator reads, and a truncated report is marked as
    such by the caller.
    """
    gaps: list[str] = []
    ignored = frozenset(_IGNORED_NAMES)
    for source_file in sorted(source_root.rglob("*")):
        if any(part in ignored for part in source_file.parts):
            continue
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source_root)
        copied = payload_root / relative
        if not copied.is_file() or copied.stat().st_size != source_file.stat().st_size:
            gaps.append(relative.as_posix())
            if len(gaps) == _FIDELITY_REPORT_LIMIT:
                break
    return tuple(gaps)


def harness_managed(*, source_root: Path) -> bool:
    """Whether this plugin root is a harness-managed install rather than a checkout.

    PUBLIC because the answer is the whole precondition for retention, and a
    caller deciding whether to expect a retained payload needs to ask the same
    question the same way. ANY repository marker above the root is enough to
    answer "checkout": an unnecessary retention would relocate a developer's
    own tree, so the ambiguous case declines rather than acts.
    """
    return not any((source_root.parent / marker).exists() for marker in _SOURCE_REPOSITORY_MARKERS)


def _payload_at(*, root: Path, retained: bool, holder: Path | None = None) -> RetainedPayload:
    scripts_root = root / "scripts"
    return RetainedPayload(
        root=root,
        scripts_root=scripts_root,
        vendor_root=scripts_root / "_vendor",
        retained=retained,
        holder=holder,
    )


def _retained_root(*, source_root: Path) -> Path | PayloadRefusal:
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
    if isinstance(release, PayloadRefusal):
        # BEFORE `mkdtemp`, so a refused provision creates no private directory
        # at all rather than one it then has to clean up.
        return release
    holder = Path(tempfile.mkdtemp(prefix=f"{_PAYLOAD_PREFIX}{release}-"))
    # The holder is removed by `finally` unless this function RETURNS a usable
    # payload. Enumerating the failures instead — which is what this did — left
    # the directory standing for every exit the list did not name, and an
    # INTERRUPT is the one that matters: a SIGINT or SIGTERM mid-copy arrives as
    # `KeyboardInterrupt` or `SystemExit`, neither of which is an `OSError`. The
    # survivor is a half-copied tree, and once this process is gone nothing can
    # tell it from a finished payload, so the next invocation to find it would
    # execute an incomplete release. A bug-class exception gets the same
    # treatment for the same reason, while still propagating.
    root = holder / _STAGED_NAME
    published = False
    try:
        try:
            _ = shutil.copytree(source_root, root, ignore=shutil.ignore_patterns(*_IGNORED_NAMES))
        except (OSError, shutil.Error) as failure:
            return PayloadRefusal(
                message=(
                    f"ERROR: livespec payload provisioning refused: copying the installed "
                    f"release at {source_root} failed, so this invocation has no payload it "
                    f"could keep running from. Nothing was claimed and no factory run was "
                    f"started. Reinstall the plugin, then retry. Cause: {failure}"
                )
            )
        missing = missing_payload_paths(root=root)
        if missing:
            # The source passed its own check moments ago, so an incomplete COPY
            # means the source changed underneath the copy — an eviction landing
            # mid-provision, which is exactly the race this module exists for.
            return PayloadRefusal(
                message=_incomplete_message(root=source_root, missing=missing, subject="copy")
            )
        gaps = payload_fidelity_gaps(source_root=source_root, payload_root=root)
        if gaps:
            return PayloadRefusal(message=_fidelity_message(root=source_root, gaps=gaps))
        published = True
        return root
    finally:
        if not published:
            shutil.rmtree(holder, ignore_errors=True)


def _fidelity_message(*, root: Path, gaps: tuple[str, ...]) -> str:
    """One actionable line: the copy is not the same release as its source."""
    truncated = " (and possibly more)" if len(gaps) == _FIDELITY_REPORT_LIMIT else ""
    return (
        f"ERROR: livespec payload provisioning refused: the copy of the plugin "
        f"installation at {root} did not land complete — {', '.join(gaps)}{truncated} "
        f"is missing or short, so this invocation would be running a DIFFERENT "
        f"release from the one installed. Nothing was claimed and no factory run "
        f"was started. Reinstall the plugin, then retry."
    )


def _incomplete_message(*, root: Path, missing: tuple[str, ...], subject: str) -> str:
    """One actionable line naming WHAT is missing and WHICH tree it is missing from."""
    return (
        f"ERROR: livespec payload provisioning refused: the plugin {subject} at {root} "
        f"is missing {', '.join(missing)}, so this invocation has no complete payload "
        f"to keep running from. Nothing was claimed and no factory run was started. "
        f"Reinstall the plugin, then retry."
    )


def _release_identity(*, source_root: Path) -> str | PayloadRefusal:
    """The released version this payload carries, or a refusal naming the fault.

    Four distinct faults, one verdict: unreadable, unparseable, not an object,
    and no usable `version`. Each is reported with its own cause so an operator
    is told which one to fix, and none of them falls through to a placeholder.
    """
    manifest = source_root / _RELEASE_MANIFEST
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError as failure:
        return _provenance_refusal(root=source_root, cause=f"it could not be read ({failure})")
    try:
        parsed = json.loads(text)
    except ValueError as failure:
        return _provenance_refusal(root=source_root, cause=f"it is not valid JSON ({failure})")
    if not isinstance(parsed, dict):
        return _provenance_refusal(root=source_root, cause="its top level is not a JSON object")
    version = cast("dict[str, object]", parsed).get(_RELEASE_KEY)
    if not isinstance(version, str) or not version.strip():
        return _provenance_refusal(
            root=source_root, cause=f"it declares no usable {_RELEASE_KEY!r} string"
        )
    return version.strip()


def _provenance_refusal(*, root: Path, cause: str) -> PayloadRefusal:
    """One actionable line naming the manifest, the fault, and that nothing ran."""
    return PayloadRefusal(
        message=(
            f"ERROR: livespec payload provisioning refused: the plugin installation "
            f"at {root} carries a {_RELEASE_MANIFEST} this launcher cannot establish a "
            f"release from — {cause}. The release is the payload's provenance, which "
            f"the minimum-release floor and the build-currency findings compare "
            f"against other builds, so it cannot be substituted. Nothing was claimed "
            f"and no factory run was started. Reinstall the plugin, then retry."
        )
    )


def payload_relative_argv(
    *, argv: Sequence[str], source_root: Path, payload_root: Path
) -> list[str]:
    """Re-point an argv whose program lives in the SOURCE tree at the payload copy.

    The credential self-heal re-execs this process through the project's
    `credential_wrapper`, and it builds that command from `sys.argv` — whose
    first element is the installed path the shell invoked. If the harness
    evicts the installation around that re-exec, the interpreter cannot open
    the script it was handed: the invocation dies before any application code,
    for precisely the reason retention exists. Measured as exit 2 reported
    through the wrapper-launch diagnostic, which blames the wrapper for a
    missing file.

    The payload is a whole-tree copy of the source, so every path under the
    source has an exact counterpart under the payload, and re-pointing the
    program at its own copy is a rename of the same bytes rather than a change
    of build. ONLY the program is re-pointed: the remaining operands belong to
    the caller and may legitimately name paths in any tree, including the one
    being evicted.

    An argv whose program is NOT under the source root is returned unchanged —
    a `-c` invocation, an absolute path into some other tree, a path that
    cannot be resolved at all — because there is no counterpart to re-point it
    to. `resolve()` reports an unresolvable path three different ways across
    the supported interpreters (`RuntimeError` for a symlink loop on 3.10 and
    3.12, `OSError` for other filesystem faults, `ValueError` for an embedded
    NUL), and all three mean the same thing here, so all three fall through to
    the unchanged argv rather than turning a cosmetic path fault into a dead
    launcher.
    """
    if not argv:
        return list(argv)
    try:
        relative = Path(argv[0]).resolve().relative_to(source_root.resolve())
    except (OSError, RuntimeError, ValueError):
        return list(argv)
    return [str(payload_root.joinpath(relative)), *argv[1:]]
