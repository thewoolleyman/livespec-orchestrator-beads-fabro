# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""ci_wires_repo_local_gates — the repo-local gates run in CI and on a payload-only push.

`SPECIFICATION/constraints.md`, the fleet-toolchain-literal-ban bullet, ratifies
that ban as run by the check aggregate, pre-push AND CI, "so a new hardcoded
premise cannot be reintroduced by a later change"; and the typed-workflow-inputs
clause of the repository-integration-contract section requires a CI check to
enforce seam equivalence. Both gates are repo-local (`dev-tooling/checks/`),
and the CI workflow enumerates its batches by hand rather than running the
aggregate, so a repo-local gate is wired into CI only if someone remembers to
name it there. The `check-ci-matrix-completeness` guard covers canonical
dev-tooling slugs only; this module is the same guard for these repo-local ones.

TWO VENUES, BECAUSE THE PAYLOAD IS NOT PYTHON. The pre-push hook routes a push
with zero `.py` changes to the doc-only target list — which is exactly the
route a change to `workflow.toml`, `workflow.fabro` or a prompt file takes. A
gate absent from that list never runs on the pushes it exists to catch, so the
doc-only target list is checked alongside the CI batch.

TWO POSITIVE CONTROLS, because this check reports an ABSENCE for a living: the
CI metadata batch step must be FOUND (a renamed step would otherwise read as
"nothing missing"), and every guarded slug must name a real justfile recipe (a
misspelled slug would otherwise be reported missing forever, or never at all).
The guard names itself among the guarded slugs, so its own wiring cannot
silently lapse either.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
for _path in (_SCRIPT_DIR, _SCRIPTS, _SCRIPTS / "_vendor"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script; it
# is imported from the installed shared dev-tooling package's vendored copy.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
if str(_DT_VENDOR) not in sys.path:
    sys.path.insert(0, str(_DT_VENDOR))

import structlog  # noqa: E402

__all__: list[str] = ["REQUIRED_SLUGS", "findings", "main"]

# The repo-local gates that MUST run in CI and on a payload-only push, plus
# this guard itself. `check-fabro-graph-validity` joined after it sat in the
# local aggregate for a whole release while CI never ran it (bd-ib-6t4): an
# invalid factory graph takes the whole factory down, so its absence from CI is
# the most expensive one this guard can catch.
REQUIRED_SLUGS: tuple[str, ...] = (
    "check-no-fleet-toolchain-literals",
    "check-seam-equivalence",
    "check-fabro-graph-validity",
    "check-ci-wires-repo-local-gates",
)

_WORKFLOW = Path(".github") / "workflows" / "ci.yml"
_DOC_ONLY = Path("dev-tooling") / "just-check-pre-commit-doc-only.sh"
_JUSTFILE = Path("justfile")

# The unconditional CI step that runs every repo-local metadata check.
_BATCH_ANCHOR = "Run the batched metadata checks"
_BATCH_STEP_RE = re.compile(
    r"(?ms)^\s*- name: " + re.escape(_BATCH_ANCHOR) + r"\s*$(?P<body>.*?)(?=^\s*- name: |\Z)"
)
_TARGETS_RE = re.compile(r"(?ms)^targets=\((?P<body>.*?)^\)")
_RECIPE_RE = re.compile(r"(?m)^([A-Za-z0-9_-]+):")


def _batch_step(*, workflow_text: str) -> str | None:
    match = _BATCH_STEP_RE.search(workflow_text)
    return None if match is None else match.group("body")


def _invoked(*, batch_text: str, slug: str) -> bool:
    return re.search(rf"(?m)^\s*just {re.escape(slug)}(?:\s|$)", batch_text) is not None


def _doc_only_targets(*, script_text: str) -> frozenset[str]:
    """Every real target token, ignoring comment lines and trailing comments.

    Splitting the whole block on whitespace would count a slug named inside a
    shell comment as a wired target — and the likeliest comment to sit in that
    block is a note recording which slugs are deliberately absent, which is
    exactly what this check reports. Everything from an unquoted `#` to the end
    of the line is dropped, which covers both a whole-line comment and a
    trailing one; a target slug can never contain a `#`.
    """
    match = _TARGETS_RE.search(script_text)
    body = "" if match is None else match.group("body")
    return frozenset(token for line in body.splitlines() for token in line.split("#", 1)[0].split())


def _recipes(*, justfile_text: str) -> frozenset[str]:
    return frozenset(_RECIPE_RE.findall(justfile_text))


def findings(*, repo_root: Path) -> list[str]:
    """Every guarded slug missing from a venue, plus every failed control."""
    batch = _batch_step(workflow_text=(repo_root / _WORKFLOW).read_text(encoding="utf-8"))
    recipes = _recipes(justfile_text=(repo_root / _JUSTFILE).read_text(encoding="utf-8"))
    doc_only = _doc_only_targets(script_text=(repo_root / _DOC_ONLY).read_text(encoding="utf-8"))
    found: list[str] = []
    if batch is None:
        found.append(f"control: the CI step '{_BATCH_ANCHOR}' was not found in {_WORKFLOW}")
    for slug in REQUIRED_SLUGS:
        if slug not in recipes:
            found.append(f"control: guarded slug {slug} names no recipe in {_JUSTFILE}")
            continue
        if batch is not None and not _invoked(batch_text=batch, slug=slug):
            found.append(f"{slug} is not invoked by the CI metadata batch in {_WORKFLOW}")
        if slug not in doc_only:
            found.append(f"{slug} is absent from the doc-only pre-push target list in {_DOC_ONLY}")
    return found


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("ci_wires_repo_local_gates")
    found = findings(repo_root=_REPO_ROOT)
    for finding in found:
        log.error(finding, kind="control" if finding.startswith("control:") else "wiring")
    return 1 if found else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
