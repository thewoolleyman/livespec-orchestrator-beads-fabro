# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""tests_no_real_time — a test may not wait on, or assert about, the host clock.

Flaky master tests accounted for 9 of 37 defective factory endings after the
factory stability freeze, and all of them shared ONE shape: a real sleep plus a
tight elapsed bound, which passes on an idle laptop and fails on a loaded
factory host. The remedy is not a wider bound — that keeps the real-time
dependence and only moves the threshold — so this gate refuses the shape
itself. A test waits on a DETERMINISTIC EVENT (a joined thread, a set
`threading.Event`, a written file) and asserts on an INJECTED clock's readings
or on the ORDERING of those events.

TWO FORMS ARE REFUSED — a `time.sleep` call, and an `assert` reading a
DIFFERENCE of real clock readings. WHAT COUNTS AS EITHER, and what the
instrument deliberately cannot see, belongs to the sibling private module
`_tests_real_time_matcher`: the two concerns change for different reasons, so
that one owns the AST question and this one owns which files are looked at, how
an occurrence is stood down, and the controls. Read its docstring before
widening or narrowing the match.

THE EXEMPTION IS PER OCCURRENCE AND CARRIES ITS REASON IN THE SOURCE. A test
whose SUBJECT is real time — a shipped guard enforcing an absolute wall-clock
epoch against real processes, a poll of a live external server, a retired
hypothesis deadline — cannot be written against an injected clock, so the
marker `real-time-required: <reason>` on one of the offending expression's own
lines stands it down. A marker with NO reason is a finding of its own rather
than a pass: an exemption nobody justified is the shape this gate exists to
stop, and accepting a bare marker would make the written reason advisory.

TWO POSITIVE CONTROLS, because this check reports an ABSENCE for a living and a
scan that walked the wrong tree prints exactly what a clean suite prints. The
DISCOVERY control requires the tests walk to return a plausible number of files;
the MATCHER control requires the committed fixture's own marked lines to be
found, so a matcher that stopped recognising a form fails loudly instead of
certifying every test file in the repository.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
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
# APPEND, never insert at the front: that `_vendor` also carries a PARTIAL
# `livespec_runtime`, and putting it ahead of this repo's own `_vendor` shadows
# the full copy every plugin module imports.
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

import structlog  # noqa: E402
from _tests_real_time_matcher import offences  # noqa: E402

__all__: list[str] = [
    "EXEMPTION_MARKER",
    "MINIMUM_SCANNED_FILES",
    "file_findings",
    "findings",
    "main",
]

# The per-occurrence stand-down. It is matched as a substring of a source line
# so it works in a `#` comment wherever the offending expression reaches, and
# the text after it IS the written reason.
EXEMPTION_MARKER = "real-time-required:"

# The discovery control's floor. The tests tree held 860 `.py` files when this
# gate landed, so a walk returning fewer than half that has lost the tree rather
# than found a clean one.
MINIMUM_SCANNED_FILES = 400

_TESTS_TREE = "tests"
_CONTROL_FIXTURE = Path("dev-tooling") / "checks" / "fixtures" / "real_time_control.py.txt"
# Every line the matcher must flag in the control fixture carries the first
# marker; every line that must also survive exemption carries the second.
_EXPECT_OFFENCE = "EXPECT-OFFENCE"
_EXPECT_REPORTED = "EXPECT-REPORTED"

_UNREASONED_FINDING = "carries an exemption marker with no written reason"


def _exemption(*, lines: Sequence[str], first: int, last: int) -> tuple[bool, bool]:
    """Whether a marker binds to this occurrence, and whether it carries a reason.

    The binding region is the offending expression's own lines PLUS the one line
    immediately above it. The lead-in line is not laxity: a reason worth reading
    rarely fits after `time.sleep(_SETTLE_SECONDS)` inside this repository's
    100-column limit, and the alternative authors reach for is a reason trimmed
    until it says nothing. One line of lead-in keeps the marker bound to the
    single occurrence it stands down, which a file-level pragma would not.
    """
    reasons = [
        line.partition(EXEMPTION_MARKER)[2].strip()
        for line in lines[max(0, first - 2) : last]
        if EXEMPTION_MARKER in line
    ]
    return (bool(reasons), any(reasons))


def file_findings(*, source: str, label: str) -> list[str]:
    """Every surviving offence in one test file, each naming its file and line."""
    lines = source.splitlines()
    found: list[str] = []
    for first, last, what in offences(source=source):
        marked, reasoned = _exemption(lines=lines, first=first, last=last)
        if reasoned:
            continue
        reason = _UNREASONED_FINDING if marked else what
        found.append(f"{label}:{first}: {reason}")
    return found


def _matcher_control(*, repo_root: Path) -> list[str]:
    """The fixture's own marked lines must be found, and only those reported."""
    path = repo_root / _CONTROL_FIXTURE
    if not path.is_file():
        return [f"control: the matcher control fixture {_CONTROL_FIXTURE} is missing"]
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    marked = {
        marker: frozenset(number for number, line in enumerate(lines, start=1) if marker in line)
        for marker in (_EXPECT_OFFENCE, _EXPECT_REPORTED)
    }
    detected = frozenset(first for first, _, _ in offences(source=source))
    reported = frozenset(
        int(finding.split(":")[1]) for finding in file_findings(source=source, label="control")
    )
    disagreements = [
        (verb, sorted(observed), sorted(marked[marker]))
        for verb, observed, marker in (
            ("detected", detected, _EXPECT_OFFENCE),
            ("reported", reported, _EXPECT_REPORTED),
        )
        if observed != marked[marker]
    ]
    fixture = _CONTROL_FIXTURE
    return [
        f"control: the matcher {verb} {found} in {fixture}; its markers say {marks}"
        for verb, found, marks in disagreements
    ]


def findings(*, repo_root: Path) -> list[str]:
    """Every surviving offence under `tests/`, plus every failed control."""
    paths = sorted((repo_root / _TESTS_TREE).rglob("*.py"))
    found = [
        finding
        for path in paths
        for finding in file_findings(
            source=path.read_text(encoding="utf-8"),
            label=path.relative_to(repo_root).as_posix(),
        )
    ]
    scanned, floor = len(paths), MINIMUM_SCANNED_FILES
    if scanned < floor:
        found.append(f"control: the {_TESTS_TREE} walk returned {scanned}, below {floor}")
    found.extend(_matcher_control(repo_root=repo_root))
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
    log = structlog.get_logger("tests_no_real_time")
    found = findings(repo_root=_REPO_ROOT)
    for finding in found:
        log.error(finding, kind="control" if finding.startswith("control:") else "real-time")
    return 1 if found else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
