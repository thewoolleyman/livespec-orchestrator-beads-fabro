"""Plan-archive refusal type and the working-tree reference gate.

The LEDGER-side archive gates live elsewhere: `_plan_archive_review` owns
child disposition and completeness-review evidence, and `_plan_proof_leg`
owns the third one, the verified plan Proof of Done record. This module
owns the refusal TYPE all three raise, plus the one gate that is not a
ledger read at all.

None of the three reads the working
tree, so an archive could rename `plan/<slug>/` out from under code that
addresses that directory by path. Archiving `beads-v1-1-2-upgrade` on
2026-09-04 moved a rehearsal package two live test modules held as
hardcoded path constants: the archive pull request came back with 33
`FileNotFoundError`s and a red per-file-coverage leg, on a move whose
epic the same call had already closed and stamped.

That WORKING-TREE gate sweeps everything outside `plan/` for files that
address `plan/<slug>/` and refuses the move while any exist, naming every
one, so the driving session repoints or retires each hit in the same pull
request as the move.

Two path spellings reach the same directory and both must be caught: the
posix literal `plan/<slug>/…` and the segment-join form
`ROOT / "plan" / "<slug>" / …` — the shape BOTH measured instances used.
The sweep therefore collapses each separator together with the quoting
and whitespace around it before matching, so one pattern covers both. The
match is bounded on its right so that a longer slug sharing the prefix
(`plan/<slug>-successor`) is not a hit, and label strings of the form
`origin:<slug>` never match because they carry no separator at all.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

__all__: list[str] = [
    "PlanArchiveRefusedError",
    "outside_plan_path_references",
]

EXCLUDED_DIRECTORY_NAMES: tuple[str, ...] = (
    ".git",
    ".venv",
    "_vendor",
    "node_modules",
)

# Repo-relative trees the sweep never reports. `SPECIFICATION/history` holds
# RATIFIED SNAPSHOTS: a proposal's text is the record of what it said when it
# was ratified, so repointing a path inside it would falsify history rather
# than fix a reference. Excluded by relative path, not by directory NAME, so an
# ordinary directory called `history` elsewhere is still swept.
EXCLUDED_RELATIVE_DIRECTORIES: tuple[str, ...] = ("SPECIFICATION/history",)

_PLAN_DIR = "plan"
# A separator plus the quoting and whitespace hugging it, so a segment-join
# path renders as the posix path it builds.
_SEPARATOR_NOISE = re.compile(r"[\"'\s]*/[\"'\s]*")


class PlanArchiveRefusedError(Exception):
    """Expected refusal raised when a plan cannot be archived."""

    @classmethod
    def missing_completeness_review(cls) -> PlanArchiveRefusedError:
        return cls("independent completeness-review evidence is required")

    @classmethod
    def unresolved_publishing_identity(cls, *, role: str) -> PlanArchiveRefusedError:
        """Refuse while one party to the completeness leg cannot be named.

        DISTINCT from `missing_completeness_review` because the remedy is
        ENVIRONMENTAL — drive the operation from an agent session, or from a host
        whose forge token resolves a login — rather than a review somebody still
        has to perform. Reporting the generic refusal here would send its reader
        off to commission a review that the gate could not grade either.
        """
        cause = f"no publishing identity could be computed, so the {role} cannot be named"
        consequence = "the completeness leg compares the archiving identity against the"
        detail = "reviewer's, and a comparison with one side unknown is no check at all"
        return cls(f"{cause}; {consequence} {detail}")

    @classmethod
    def undisposed_children(cls, *, child_ids: list[str]) -> PlanArchiveRefusedError:
        return cls(f"undisposed child work-items: {', '.join(child_ids)}")

    @classmethod
    def outside_path_references(
        cls,
        *,
        slug: str,
        paths: tuple[str, ...],
    ) -> PlanArchiveRefusedError:
        joined = ", ".join(paths)
        return cls(f"files outside plan/ reference plan/{slug}/: {joined}")

    @classmethod
    def missing_plan_definition_of_done(cls, *, epic_id: str) -> PlanArchiveRefusedError:
        """Name the missing section the proof leg has nothing to grade without.

        The proof leg opens by requiring the section, and this refusal is
        distinct from the unproved-assertions one because the remedy differs:
        author the section with the maintainer, rather than publish a record.
        """
        section = "no gradeable Definition of Done section"
        consequence = "the archive proof leg has no plan assertions to prove"
        remedy = "author the section with the maintainer's own statement of what done means first"
        return cls(f"epic {epic_id} carries {section}, so {consequence}; {remedy}")

    @classmethod
    def unproved_plan_assertions(
        cls,
        *,
        unproved: tuple[str, ...],
        rejected: tuple[str, ...],
    ) -> PlanArchiveRefusedError:
        """Name every unproved plan assertion, and every record the gate rejected.

        Both halves are carried because they prescribe different next actions: an
        assertion nobody has published for needs a capture and an independent
        replay, while a published record the gate rejected needs republishing
        against the released build. Naming only the assertions leaves an operator
        who DID publish unable to see that their record was read and refused.
        """
        named = "; ".join(unproved)
        detail = f" Records rejected: {'; '.join(rejected)}." if rejected else ""
        return cls(
            f"no verified plan Proof of Done record proves these plan assertions: {named}.{detail}"
        )


def outside_plan_path_references(*, project_root: Path, slug: str) -> tuple[str, ...]:
    """Return repo-relative paths outside `plan/` that address `plan/<slug>/`."""
    pattern = re.compile(rf"{_PLAN_DIR}/{re.escape(slug)}(?![0-9A-Za-z_-])")
    swept = _swept_files(root=project_root, plan_tree=project_root / _PLAN_DIR)
    ignored = _gitignored_paths(root=project_root, paths=swept)
    return tuple(
        sorted(
            path.relative_to(project_root).as_posix()
            for path in swept
            if path not in ignored and _addresses_plan_path(path=path, pattern=pattern)
        )
    )


def _gitignored_paths(*, root: Path, paths: list[Path]) -> frozenset[Path]:
    """The swept paths git ignores; empty when that cannot be established.

    A gitignored file is not in the pull request the archive move lands in, so
    it cannot be the red-pull-request hazard this sweep guards. Resolved in ONE
    batched `check-ignore` rather than per file, because the sweep already walks
    the whole tree and a fork per file is what made an earlier liveness guard
    unusable.

    An empty set on ANY failure is the fail-CLOSED direction here: it reports
    more hits, never fewer, so a broken or absent git never lets a real
    reference through unseen.
    """
    if not paths:
        return frozenset()
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, paths on stdin.
            ["git", "-C", str(root), "check-ignore", "--stdin"],  # noqa: S607
            input="\n".join(str(path) for path in paths),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return frozenset()
    return frozenset(Path(line) for line in completed.stdout.splitlines() if line)


def _swept_files(*, root: Path, plan_tree: Path) -> list[Path]:
    found: list[Path] = []
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            # Pruned rather than filtered afterwards: descending into `.git`
            # or a `node_modules` costs more than the archive it guards.
            excluded_relative = entry.as_posix().endswith(EXCLUDED_RELATIVE_DIRECTORIES)
            if (
                entry != plan_tree
                and entry.name not in EXCLUDED_DIRECTORY_NAMES
                and not excluded_relative
            ):
                found.extend(_swept_files(root=entry, plan_tree=plan_tree))
        else:
            found.append(entry)
    return found


def _addresses_plan_path(*, path: Path, pattern: re.Pattern[str]) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # A binary artifact or an unreadable entry addresses nothing a test
        # could import; it is skipped rather than reported as a hit.
        return False
    return pattern.search(_SEPARATOR_NOISE.sub("/", text)) is not None
