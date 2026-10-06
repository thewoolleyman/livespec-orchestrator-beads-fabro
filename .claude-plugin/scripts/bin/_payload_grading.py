"""Grade whether a tree is a USABLE payload, and whether it is the SAME release.

Cut out of `_payload` along its own cohesion seam. That module DECIDES and
PROVISIONS: it resolves which tree an invocation runs from, copies a release
aside, publishes it to children and removes it at exit. Underneath it sat this
layer, which answers plain factual questions about a tree instead — which
required members it cannot supply, and which files it holds that differ from
the source it was copied from — and phrases the refusal those answers justify.

It traffics only in paths and tuples of strings, and names none of
`_payload`'s types: no `RetainedPayload`, no `PayloadRefusal`. That one-way
dependency is what makes the cut clean — this module imports nothing from
`_payload`.

The split was forced by size. Recording a payload's SOURCE so an inherited
tree is reused only when it came from the same place took `_payload` past its
250 LLOC hard ceiling, and the remedy for a file over the ceiling is to
decompose it by cohesion, never to shave lines.

`fidelity_message` and `incomplete_message` are PUBLIC here where they were
private in `_payload`, because they are now consumed across a module boundary:
a `_`-prefixed name imported elsewhere is rejected by pyright strict
(`reportPrivateUsage`) and by the private-calls check alike. `IGNORED_NAMES`
is public for the same reason — `_payload`'s `copytree` and this module's
fidelity walk must agree on what the copy deliberately drops, so the tuple has
to be one shared constant rather than two that could drift.

`_payload` re-exports `missing_payload_paths` and `payload_fidelity_gaps` in
its own `__all__`: they were part of its published surface before this cut and
callers import them from there.

Stdlib only, and no `livespec_orchestrator_beads_fabro` or `livespec_runtime`
import: this is reached from the pre-import launcher, before `bootstrap()`
puts either tree on `sys.path`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

__all__: list[str] = [
    "FIDELITY_REPORT_LIMIT",
    "IGNORED_NAMES",
    "fidelity_message",
    "incomplete_message",
    "inventory_gaps",
    "missing_payload_paths",
    "payload_fidelity_gaps",
    "source_inventory",
]

# How much of a file is read at a time when digesting it. The whole tree is a
# few megabytes, so this is about not holding a large asset in memory rather
# than about throughput.
_DIGEST_CHUNK_BYTES = 65536

# Byte-compiled caches are reproducible from the sources beside them, so they
# are the one thing the copy leaves behind.
IGNORED_NAMES = ("__pycache__",)
# How many differing paths a fidelity refusal names. An operator needs enough
# to recognise WHAT is missing, not the whole set.
FIDELITY_REPORT_LIMIT = 5
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

    Returns at most `FIDELITY_REPORT_LIMIT` paths. The whole set is not
    useful in a refusal an operator reads, and a truncated report is marked as
    such by the caller.
    """
    gaps: list[str] = []
    ignored = frozenset(IGNORED_NAMES)
    for source_file in sorted(source_root.rglob("*")):
        if any(part in ignored for part in source_file.parts):
            continue
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source_root)
        copied = payload_root / relative
        if not copied.is_file() or copied.stat().st_size != source_file.stat().st_size:
            gaps.append(relative.as_posix())
            if len(gaps) == FIDELITY_REPORT_LIMIT:
                break
    return tuple(gaps)


def source_inventory(*, root: Path) -> dict[str, str]:
    """Every file under `root`, as POSIX relative path to content digest.

    Taken BEFORE the copy, which is the whole reason this exists. A post-copy
    walk of the source answers "does the copy match the source AS IT NOW
    STANDS", and that question has two wrong answers available: a member the
    copy omitted is invisible once the source has lost it too, and a source
    that legitimately moved on after a complete copy looks like a divergence.
    An inventory taken first answers the question that actually matters —
    "does the copy match the release it was made from" — and it is what lets a
    coherent payload survive its source changing afterwards.

    DIGESTS, not sizes. Size equality cannot see a file copied with wrong
    bytes at the same length, which is the second case this replaces. The
    trade-off recorded here previously ("size, not content hash") was a
    premature optimisation at this scale: measured 0.015s for 731 files over
    5MB, against a copy of the same tree.

    A file that cannot be read is recorded with a digest no readable file can
    produce, so it reports as a divergence rather than raising out of the
    pre-import launcher or silently matching.

    This is SAME-RELEASE coherence, not integrity. It detects a copy that did
    not land faithfully; it establishes nothing about whether the source was
    trustworthy, and it is not a tamper or supply-chain control.
    """
    ignored = frozenset(IGNORED_NAMES)
    inventory: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if any(part in ignored for part in path.parts) or not path.is_file():
            continue
        inventory[path.relative_to(root).as_posix()] = _digest(path=path)
    return inventory


def _digest(*, path: Path) -> str:
    """The file's SHA-256, or the unreadable sentinel."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_DIGEST_CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError:
        return "unreadable"
    return digest.hexdigest()


def inventory_gaps(*, inventory: dict[str, str], payload_root: Path) -> tuple[str, ...]:
    """Inventory entries the payload cannot reproduce, as POSIX relative paths.

    "Cannot reproduce" is absent, unreadable, or present with different
    content. Returns at most `FIDELITY_REPORT_LIMIT` paths, like its
    size-based predecessor, because a refusal an operator reads needs enough
    to recognise the fault rather than the whole set.
    """
    gaps: list[str] = []
    for relative, expected in sorted(inventory.items()):
        copied = payload_root / relative
        if not copied.is_file() or _digest(path=copied) != expected:
            gaps.append(relative)
            if len(gaps) == FIDELITY_REPORT_LIMIT:
                break
    return tuple(gaps)


def fidelity_message(*, root: Path, gaps: tuple[str, ...]) -> str:
    """One actionable line: the copy is not the same release as its source."""
    truncated = " (and possibly more)" if len(gaps) == FIDELITY_REPORT_LIMIT else ""
    return (
        f"ERROR: livespec payload provisioning refused: the copy of the plugin "
        f"installation at {root} did not land complete — {', '.join(gaps)}{truncated} "
        f"is missing or short, so this invocation would be running a DIFFERENT "
        f"release from the one installed. Nothing was claimed and no factory run "
        f"was started. Reinstall the plugin, then retry."
    )


def incomplete_message(*, root: Path, missing: tuple[str, ...], subject: str) -> str:
    """One actionable line naming WHAT is missing and WHICH tree it is missing from."""
    return (
        f"ERROR: livespec payload provisioning refused: the plugin {subject} at {root} "
        f"is missing {', '.join(missing)}, so this invocation has no complete payload "
        f"to keep running from. Nothing was claimed and no factory run was started. "
        f"Reinstall the plugin, then retry."
    )
