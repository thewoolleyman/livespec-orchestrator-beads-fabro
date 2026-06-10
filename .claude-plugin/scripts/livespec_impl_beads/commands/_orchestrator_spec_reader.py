"""`orchestrator spec-reader` subcommand — expose the spec BY CATEGORY.

Per livespec/SPECIFICATION/contracts.md §"Orchestrator CLI contract —
the three named CLIs", the spec-reader CLI's one normative property is
category exposure: it MUST expose spec content by template category
(spec / contracts / constraints / scenarios / …) so a consumer can
tell what is a scenario — it categorizes, never conceals. Every file
in the live spec tree appears under exactly one category; nothing is
held back.

Category derivation (deterministic, total): a top-level file's
category is its lowercased filename stem (`spec.md` → `spec`,
`contracts.md` → `contracts`); a nested file's category is its first
path segment (`research/foo.md` → `research`). Only ratified
canonical content is exposed — the underlying Spec Reader already
excludes `history/` and `proposed_changes/`.
"""

import json
import sys
from pathlib import Path, PurePosixPath

from livespec_impl_beads.spec_reader import read_current_specification

__all__: list[str] = ["categorize", "run_spec_reader"]

_EXIT_PRECONDITION_ERROR = 3


def run_spec_reader(*, spec_root: Path, category: str | None, as_json: bool) -> int:
    """Run the spec-reader subcommand against `spec_root`."""
    if not spec_root.is_dir():
        _ = sys.stderr.write(f"ERROR: spec tree not found: {spec_root}\n")
        return _EXIT_PRECONDITION_ERROR
    snapshot = read_current_specification(spec_root=spec_root)
    categories = categorize(files=snapshot.files)
    if category is not None:
        categories = {name: files for name, files in categories.items() if name == category}
    if as_json:
        payload = {"version": snapshot.version, "categories": categories}
        _ = sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        _write_human(version=snapshot.version, categories=categories)
    return 0


def categorize(*, files: dict[str, str]) -> dict[str, dict[str, str]]:
    """Assign every spec file to exactly one category (never conceals)."""
    categories: dict[str, dict[str, str]] = {}
    for path in sorted(files):
        categories.setdefault(_category_for(path=path), {})[path] = files[path]
    return categories


def _category_for(*, path: str) -> str:
    parts = PurePosixPath(path).parts
    if len(parts) > 1:
        return parts[0]
    return PurePosixPath(path).stem.lower()


def _write_human(*, version: int, categories: dict[str, dict[str, str]]) -> None:
    _ = sys.stdout.write(f"spec version: v{version:03d}\n")
    if not categories:
        _ = sys.stdout.write("(no spec files)\n")
        return
    for name in sorted(categories):
        _ = sys.stdout.write(f"category: {name}\n")
        for path in sorted(categories[name]):
            _ = sys.stdout.write(f"  {path}\n")
