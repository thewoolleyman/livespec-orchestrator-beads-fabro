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
import os
import shutil
import tempfile
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from _payload_grading import (
    IGNORED_NAMES,
    fidelity_message,
    incomplete_message,
    inventory_gaps,
    missing_payload_paths,
    payload_fidelity_gaps,
    source_inventory,
)

__all__: list[str] = [
    "INSTALLED_ROOT_ENV",
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
# Where the INSTALLATION this payload was copied from lives, for the processes
# that have to keep asking about the installation rather than about the code.
#
# Published because the launcher is the ONLY thing that knows the answer once
# retention has happened. `plugin_root()` resolves the installed root from
# `CLAUDE_PLUGIN_ROOT`, and when that is absent it falls back to walking up
# from its own `__file__` — which, after a copy, lands inside the PAYLOAD. On
# the Claude path the harness exports that variable so the fallback never
# matters. Normal Codex exports NOTHING, so the fallback is the whole answer
# there, and it made the candidate root and the execution path the same tree:
# the self-update canary compared the running build against itself, and a
# minimum-release refusal named a disposable directory under the system
# temporary root as the installation to update.
#
# Deliberately a SEPARATE variable from `PAYLOAD_ROOT_ENV` rather than a second
# meaning layered onto it. The two answer opposite questions — "which tree is
# this code running from" versus "which installation is present to be updated"
# — and the whole defect class this module exists for comes from conflating
# them.
INSTALLED_ROOT_ENV = "LIVESPEC_INSTALLED_PLUGIN_ROOT"

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
# What marks the tree one level above the plugin root as THIS plugin's own
# source repository. Presence of a project file is not enough: an INSTALLED
# tree that merely sits beside an unrelated `pyproject.toml` had retention
# switched off and went back to executing an evictable source — silently, which
# is the direction that re-opens the bug this module exists for.
#
# So the marker must NAME this project. `pyproject.toml` is read as text
# because the 3.10 floor ships no TOML parser, and the expected name is derived
# from the package directory already required above rather than restated as a
# second literal that could drift from it.
_SOURCE_PROJECT_FILE = "pyproject.toml"
_PACKAGE_DIRECTORY = "livespec_orchestrator_beads_fabro"
_SOURCE_PROJECT_NAME = _PACKAGE_DIRECTORY.replace("_", "-")
# A source checkout keeps the plugin root at this name; an install flattens it
# to the cache directory, which is named for the build. Both conditions must
# hold, so an ambiguous tree is RETAINED — the safe direction here, since an
# unnecessary retention costs one copy while a missed one restores the defect.
_SOURCE_PLUGIN_ROOT_NAME = ".claude-plugin"
# The holder-level record of WHICH source tree a payload was copied from.
#
# It lives in the HOLDER, beside `payload/` rather than inside it, for two
# reasons. The payload stays a faithful whole-tree copy of its source, so
# `payload_fidelity_gaps` keeps comparing like with like; and the record shares
# the holder's lifetime exactly, so it cannot outlive the tree it describes.
#
# Written only once a provision has passed every completeness and fidelity
# grade, immediately before the payload is published, so an interrupted or
# refused provision leaves neither an adoptable tree NOR a record claiming one.
_SOURCE_RECORD = "source"


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
    inherited = _inherited_payload(environ=environ, source_root=source_root)
    if inherited is not None:
        return inherited
    if not harness_managed(source_root=source_root):
        # A checkout IS its own installation, so it publishes itself. Omitting
        # this left a FOREIGN install standing as the candidate whenever the
        # record was inherited: measured at a checkout executing release 5.5.5
        # while every currency surface reported on install A at 7.1.0. The
        # `__file__` fallback would have answered correctly, but only when no
        # record exists at all, and a record that does exist outranks it.
        environ[INSTALLED_ROOT_ENV] = str(source_root.resolve())
        return _payload_at(root=source_root, retained=False)
    missing = missing_payload_paths(root=source_root)
    if missing:
        return PayloadRefusal(
            message=incomplete_message(root=source_root, missing=missing, subject="installation")
        )
    retained = _retained_root(source_root=source_root)
    if isinstance(retained, PayloadRefusal):
        return retained
    environ[PAYLOAD_ROOT_ENV] = str(retained)
    # ASSIGNED, not `setdefault`. Reaching here means this invocation SELECTED
    # an installation and copied it, so that source IS the installation and it
    # is the candidate — whatever a parent recorded.
    #
    # `setdefault` was the defect: it is a no-op on an inherited key, so
    # selecting a different install kept the OLD candidate. Measured at install
    # B's release 9.9.9 executing while the candidate still named install A, so
    # a minimum-release refusal would have told the operator to update A.
    #
    # ADOPTION is the case this must not touch, and it is already separated by
    # control flow rather than by a condition here: an inherited payload
    # returns at the top of this function, so a same-source helper keeps its
    # parent's record untouched. That distinction is load-bearing — a helper's
    # own `source_root` is the PAYLOAD, so assigning on that path would record
    # the payload as the installation and collapse the candidate onto the
    # execution path again.
    environ[INSTALLED_ROOT_ENV] = str(source_root.resolve())
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


def _inherited_payload(
    *, environ: MutableMapping[str, str], source_root: Path
) -> RetainedPayload | None:
    """Adopt the payload a parent published, when it is complete AND from here.

    An incomplete or vanished inherited payload falls through to a fresh
    provision rather than refusing: the parent may have exited and cleaned up,
    and a child that can still provision for itself should. Nothing here is
    ADOPTED on trust — the same completeness contract a fresh copy must pass
    is applied before this tree is executed.

    `source_root` is what separates the two questions this variable used to
    conflate. The hand-down exists so the several processes of ONE dispatch
    read one tree, and that case is `source_root` matching the payload's
    recorded origin. But the variable is ordinary inherited environment, so it
    also reaches a process pointed at a DIFFERENT installation on purpose — a
    dispatch launched from inside another, a helper invoked from an explicitly
    named newer install, a developer running their own checkout from a shell
    that still carries a parent's payload. Adoption was unconditional, so the
    inherited tree won and the selected release was silently ignored; measured
    at 7.1.0 executing where 9.9.9 was named, and at an inherited payload
    displacing this project's own source checkout.

    A mismatch falls through to a fresh provision for the tree that WAS
    selected, so the explicit choice decides and nothing is refused.
    """
    recorded = environ.get(PAYLOAD_ROOT_ENV, "")
    if not recorded:
        return None
    root = Path(recorded)
    if missing_payload_paths(root=root):
        return None
    if not _payload_serves(payload_root=root, source_root=source_root):
        return None
    return _payload_at(root=root, retained=True)


def _payload_serves(*, payload_root: Path, source_root: Path) -> bool:
    """Whether an inherited payload is the right tree for `source_root`.

    TWO shapes qualify, and they are the two the hand-down exists for. The
    selected source may be the installation this payload was COPIED FROM — the
    ordinary case, where `drive` publishes and the `dispatcher.py` it starts
    inherits. Or the selected source may BE the payload: a `scripts/bin/`
    helper spawned from inside the payload resolves its own plugin root to the
    payload tree, so that is the source it names, and the payload is
    self-evidently the right answer for it. Omitting this second shape made
    every owned helper copy the copy instead of reusing its parent's tree.

    Anything else names a DIFFERENT installation, and the explicit selection
    wins.
    """
    selected = str(source_root.resolve())
    return selected in {_recorded_source(payload_root=payload_root), str(payload_root.resolve())}


def harness_managed(*, source_root: Path) -> bool:
    """Whether this plugin root is a harness-managed install rather than a checkout.

    PUBLIC because the answer is the whole precondition for retention, and a
    caller deciding whether to expect a retained payload needs to ask the same
    question the same way.

    "Checkout" requires BOTH that the plugin root carries the name a checkout
    gives it and that the tree above it is THIS project's repository, named as
    such in its own `pyproject.toml`. Either alone is too weak: a cache
    directory can sit beside any project's files, and a directory can be
    called anything. Anything short of both is treated as harness-managed,
    because an unnecessary retention costs one copy while a missed one puts a
    live dispatch back on an evictable tree.
    """
    if source_root.name != _SOURCE_PLUGIN_ROOT_NAME:
        return True
    return not _declares_this_project(project_file=source_root.parent / _SOURCE_PROJECT_FILE)


def _declares_this_project(*, project_file: Path) -> bool:
    """Whether `project_file` is THIS project's `pyproject.toml`.

    Read as TEXT: the 3.10 floor ships no `tomllib`, and vendoring a parser
    into the pre-import launcher to answer one question would be its own
    hazard. The match is on the `name = "<project>"` assignment, which a
    dependency entry of the same name does not produce.
    """
    try:
        text = project_file.read_text(encoding="utf-8")
    except OSError:
        return False
    needle = f'name = "{_SOURCE_PROJECT_NAME}"'
    return any(line.strip() == needle for line in text.splitlines())


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
    # ALSO before `mkdtemp`, and for BOTH of this function's reasons at once.
    #
    # It must precede the COPY, because the whole point is to pin the release
    # as it stood when the copy started: a post-copy walk of the source cannot
    # see a member the copy omitted once the source has lost it too, and it
    # misreads a source that legitimately moved on after a complete copy as a
    # divergence.
    #
    # And it must precede the HOLDER, because it is the one step here that
    # reads the entire source tree, so it is the likeliest place for an
    # interrupt to land. Taken after `mkdtemp` it sat outside the `finally`
    # below and leaked the directory on any non-`OSError` fault — measured
    # with a `KeyboardInterrupt`, which left a half-built holder nothing could
    # later tell from a finished payload.
    inventory = source_inventory(root=source_root)
    destination = tempfile.gettempdir()
    try:
        holder = Path(tempfile.mkdtemp(prefix=f"{_PAYLOAD_PREFIX}{release}-"))
    except OSError as failure:
        # INSIDE the boundary: an unusable temporary destination is an
        # environment fault like any other, and it used to raise straight out
        # of the launcher as `NotADirectoryError`.
        return PayloadRefusal(
            message=(
                f"ERROR: livespec payload provisioning refused: no private directory "
                f"could be created under {destination}, so the installed release at "
                f"{source_root} cannot be copied anywhere this invocation could keep "
                f"running from. Nothing was claimed and no factory run was started. "
                f"Point TMPDIR at a writable directory, then retry. Cause: {failure}"
            )
        )
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
            _ = shutil.copytree(source_root, root, ignore=shutil.ignore_patterns(*IGNORED_NAMES))
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
                message=incomplete_message(root=source_root, missing=missing, subject="copy")
            )
        # The pre-copy inventory decides. `payload_fidelity_gaps` stays the
        # module's published size-based primitive with its own tests, but it is
        # NOT what grades a provision any more: it answers the live-source
        # question, which is the one with two wrong answers available.
        gaps = inventory_gaps(inventory=inventory, payload_root=root)
        if gaps:
            return PayloadRefusal(message=fidelity_message(root=source_root, gaps=gaps))
        # LAST, so the record exists only for a payload that passed every grade
        # above it. A record written earlier would survive a refused provision's
        # cleanup window and name a tree that was never publishable.
        _ = (holder / _SOURCE_RECORD).write_text(str(source_root.resolve()), encoding="utf-8")
        published = True
        return root
    finally:
        if not published:
            shutil.rmtree(holder, ignore_errors=True)


def _recorded_source(*, payload_root: Path) -> str:
    """Which source tree this payload was copied from, or "" when unestablished.

    An absent or unreadable record yields "", which no resolved source path can
    equal, so the payload is NOT adopted. That is the safe direction and it is
    the one this module takes everywhere else: declining to adopt costs one
    copy, while adopting a tree whose origin cannot be established is how an
    invocation silently executes a release nobody selected.
    """
    try:
        return (payload_root.parent / _SOURCE_RECORD).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


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
    label = version.strip()
    if not _usable_path_segment(label=label):
        # The label becomes part of a directory name, so PATH SYNTAX in it is
        # path syntax in the holder's path: `"../../escaped"` reached `mkdtemp`
        # as traversal and either raised or created the holder outside the
        # temporary root entirely.
        return _provenance_refusal(
            root=source_root,
            cause=(
                f"its {_RELEASE_KEY!r} is {label!r}, which is not usable as a single "
                f"path segment"
            ),
        )
    return label


def _usable_path_segment(*, label: str) -> bool:
    """Whether `label` can be embedded in a directory name as plain text.

    Rejects anything the filesystem would read as structure rather than as a
    name: a separator, a parent reference, a leading dot that would hide the
    holder, and a NUL which no path may contain.
    """
    if label in {".", ".."} or label.startswith("."):
        return False
    return not any(character in label for character in ("/", os.sep, "\\", "\0"))


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
