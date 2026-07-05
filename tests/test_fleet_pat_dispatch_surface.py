"""Tree-wide guard for retired fleet PAT references in dispatch surfaces."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOKEN = "LIVESPEC_FAMILY_GITHUB_TOKEN"
_DISPATCH_SURFACES = (
    Path("orchestrator-image"),
    Path(".claude-plugin/scripts"),
    Path(".claude-plugin/.fabro"),
    Path(".github/workflows"),
)


def _surface_files() -> list[Path]:
    files: list[Path] = []
    for surface in _DISPATCH_SURFACES:
        root = _REPO_ROOT / surface
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return sorted(files)


def test_dispatch_surfaces_do_not_reference_the_retired_fleet_pat() -> None:
    hits = [
        path.relative_to(_REPO_ROOT).as_posix()
        for path in _surface_files()
        if _TOKEN in path.read_text(encoding="utf-8")
    ]
    assert hits == []
