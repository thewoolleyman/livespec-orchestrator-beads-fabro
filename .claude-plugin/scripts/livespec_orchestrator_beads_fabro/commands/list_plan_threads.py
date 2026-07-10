"""`list-plan-threads` thin-transport command."""

import argparse
import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = ["build_envelope", "list_plan_threads", "main"]

_ARCHIVE_DIR_NAME = "archive"


def main(*, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="list-plan-threads")
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    topics = list_plan_threads(project_root=project_root)
    if args.as_json:
        _ = write_stdout(text=json.dumps(build_envelope(topics=topics), sort_keys=True) + "\n")
    else:
        for topic in topics:
            _ = write_stdout(text=f"{topic}\n")
    return 0


def list_plan_threads(*, project_root: Path) -> list[str]:
    plan_dir = project_root / "plan"
    if not plan_dir.is_dir():
        return []
    return sorted(
        child.name
        for child in plan_dir.iterdir()
        if child.name != _ARCHIVE_DIR_NAME and child.is_dir()
    )


def build_envelope(*, topics: list[str]) -> dict[str, list[str]]:
    return {"plan_threads": topics}
