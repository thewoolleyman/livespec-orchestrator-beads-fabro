# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none
"""Verify repo LOCKSTEP between the livespec-dev-tooling pin and the sandbox image tag.

This is a repo-internal CONSISTENCY guard and nothing more. It asserts that two
committed files agree: the `livespec-dev-tooling` tag pinned in `pyproject.toml`
equals the Fabro sandbox docker image tag committed in
`implement-work-item/workflow.toml`. The sandbox image is published by the
livespec-dev-tooling repository, so its tag must move in lockstep with this
repo's existing livespec-dev-tooling bump-pin surface; until shared
pin-autodiscovery learns `workflow.toml` docker images, this private check is
that lockstep guard: any bump-pin change advancing `pyproject.toml` without
advancing the Fabro sandbox image tag fails `just check`.

What it deliberately does NOT verify: it does NOT prove that a release shipped
the pin, nor that the RUNNING factory uses a fresh image. The factory runs from
the installed plugin CACHE (the last release), so this repo can be in perfect
committed lockstep while the running image is stale. Rollout is guaranteed by
authoring the image bump as a release-triggering commit (a `deps:`/`fix:` bump
that cuts a release carrying the pin), NOT by this check. The check was formerly
named `...freshness`, which wrongly implied it guaranteed a fresh rollout; it is
named `...lockstep` for the committed-file consistency it actually enforces. The
module file keeps its historical `fabro_sandbox_image_pin_freshness.py` name.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import livespec_dev_tooling

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
if str(_DT_VENDOR) not in sys.path:
    sys.path.insert(0, str(_DT_VENDOR))

import structlog  # noqa: E402

__all__: list[str] = ["main"]

_PYPROJECT = Path("pyproject.toml")
_FABRO_WORKFLOW = (
    Path(".claude-plugin") / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)
_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox"
_DEV_TOOLING_TAG_RE = re.compile(
    r'^livespec-dev-tooling\s*=\s*\{[^}]*\btag\s*=\s*"(?P<tag>[^"]+)"',
    re.MULTILINE,
)
_SANDBOX_IMAGE_RE = re.compile(
    rf'^\s*docker\s*=\s*"{re.escape(_IMAGE)}:(?P<tag>[^"]+)"',
    re.MULTILINE,
)


def _match_group(*, pattern: re.Pattern[str], text: str, group: str) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    value = match.group(group)
    return value if value != "" else None


def _read_tag(*, root: Path, path: Path, pattern: re.Pattern[str], group: str) -> str | None:
    full_path = root / path
    if not full_path.is_file():
        return None
    return _match_group(pattern=pattern, text=full_path.read_text(encoding="utf-8"), group=group)


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("fabro_sandbox_image_pin_lockstep")
    root = Path.cwd()
    dev_tooling_tag = _read_tag(
        root=root, path=_PYPROJECT, pattern=_DEV_TOOLING_TAG_RE, group="tag"
    )
    image_tag = _read_tag(root=root, path=_FABRO_WORKFLOW, pattern=_SANDBOX_IMAGE_RE, group="tag")
    if dev_tooling_tag is None or image_tag is None:
        log.error(
            "lockstep inputs not found: cannot compare pin and sandbox image tag",
            pyproject=str(_PYPROJECT),
            fabro_workflow=str(_FABRO_WORKFLOW),
            dev_tooling_tag=dev_tooling_tag,
            image_tag=image_tag,
            scope="repo-internal lockstep only; does not verify release shipped or factory rollout",
        )
        return 1
    if image_tag != dev_tooling_tag:
        log.error(
            "fabro sandbox image tag is out of lockstep with the livespec-dev-tooling pin",
            expected=dev_tooling_tag,
            actual=image_tag,
            image=_IMAGE,
            file_path=str(_FABRO_WORKFLOW),
            scope="repo-internal lockstep only; does not verify release shipped or factory rollout",
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
