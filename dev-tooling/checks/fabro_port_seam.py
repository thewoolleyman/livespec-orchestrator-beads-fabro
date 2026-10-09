# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""fabro_port_seam — the Fabro facade is the ONE place this package reaches the engine.

The Enemy Unit Test suite under `fabro-enemy-unit-tests/` exercises Fabro
through `FabroPort`, so a green pinned-versus-candidate comparison is evidence
about the DISPATCHER only where the Dispatcher reaches the engine through that
same facade. A call site that invokes the binary or the server directly is not
covered by any comparison, and nothing about its code says so: it looks exactly
like every other module, and the suite it escapes still reports green.

Measured on `origin/master` at 2026-10-09, three modules reached past the
facade — both preserve-by-reference modules built their own `fabro dump` argv,
and the ACP capability reader sent its own `/system/info` request through the
transport function — producing four findings this scan reproduces from its own
negative controls. Each one existed because the facade carried no verb for what
it needed, which is the pressure that recreates them, which is why the rule is
executable rather than a docstring.

WHAT COUNTS AS REACHING THE ENGINE. The scan is AST-based, so prose, comments
and `__all__` symbol lists are out of scope by construction. Three forms:

- `binary-argv` — a list or tuple whose FIRST element is a read of the engine
  binary: a `fabro_bin` name or attribute, a single-argument call wrapping one
  (`str(args.fabro_bin)`), or the bare constant `fabro`. Keying on the FIRST
  element is what separates an invocation from the ordinary act of passing the
  resolved path around as data, which most of this package does: a
  `FabroPort(fabro_bin=...)` construction, a `resolve_fabro_bin` call and a
  plan field all name the binary without invoking it.
- `transport-call` — a call to `fabro_http_request`, or a `send` carrying both
  a `method` and a `url` keyword, which is the `FabroHttpTransport` protocol's
  own call shape. CONSTRUCTING `UrllibFabroHttpTransport` is deliberately NOT a
  finding: two reconciler modules hand one to a port as constructor data, which
  is using the facade rather than going around it.
- `server-api-path` — a string constant opening with the server's API prefix.
  This is the form that closes the hand-rolled-urllib route: this package sends
  non-Fabro HTTP (Slack, the Messages API, OTLP export), so the urllib surface
  itself cannot be banned, but a request to a Fabro server has to name a Fabro
  route, and the facade is where those routes live.

WHAT THIS SCAN DOES NOT CLAIM. A module could in principle assemble a Fabro
route from fragments, or exec the binary through a path it computes without
ever spelling `fabro_bin`. Neither shape exists here and neither is what the
measured regressions looked like; the three forms above are the ones the
pressure actually produces. The scan is a guard against the recurrence it has
evidence for, not a proof of impossibility.

FOUR POSITIVE CONTROLS, because this check reports an ABSENCE for a living. A
broken matcher, a mis-scoped walk, or an over-wide exemption would each make it
permanently green while printing exactly what a clean repo prints, so `main`
refuses to report a clean scan unless all four hold:

- the DISCOVERY control asserts the walk reached every module that owns or
  recently held the seam, so a mis-scoped file list fails rather than certifying
  a tree it never read;
- the MATCHER control asserts the committed fixture, which carries all three
  forms, still produces one of each through the same read/parse/match path the
  package scan uses;
- the SEAM control asserts the exempt family, scanned WITHOUT its exemption,
  still yields every form — if it yielded none, the exemption would be covering
  modules that no longer hold the seam while the real invocations sat in a
  module the scan does read;
- the AIM control asserts a known Dispatcher module is NOT exempt. That is the
  one evasion the other three cannot see: widening `FAMILY_PREFIX` to `_` would
  exempt every private module in the package and report it spotless.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import ast
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
_SCRIPTS_VENDOR = _SCRIPTS / "_vendor"
for _path in (_SCRIPTS, _SCRIPTS_VENDOR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script
# (per the `no_write_direct` ban on direct `sys.stderr.write`). It is not
# vendored in this repo's own tree, so it is imported from the installed
# `livespec_dev_tooling` package's vendored copy.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
# APPEND, never insert at the front: that `_vendor` also carries a PARTIAL
# `livespec_runtime`, and putting it ahead of this repo's own `_vendor` shadows
# the full copy every plugin module imports (livespec-dev-tooling-8o8e.24 is
# the two-copies class).
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

import structlog  # noqa: E402

__all__: list[str] = [
    "AIM_ANCHOR",
    "DISCOVERY_ANCHORS",
    "FAMILY_PREFIX",
    "FORMS",
    "FORM_BINARY_ARGV",
    "FORM_SERVER_API_PATH",
    "FORM_TRANSPORT_CALL",
    "Finding",
    "control_failures",
    "family_findings",
    "fixture_path",
    "is_family_module",
    "main",
    "module_paths",
    "package_dir",
    "package_findings",
    "path_findings",
    "source_findings",
]

FORM_BINARY_ARGV = "binary-argv"
FORM_TRANSPORT_CALL = "transport-call"
FORM_SERVER_API_PATH = "server-api-path"
FORMS: tuple[str, ...] = (FORM_BINARY_ARGV, FORM_TRANSPORT_CALL, FORM_SERVER_API_PATH)

# The facade family. Every module whose FILE NAME opens with this is the seam
# itself and is therefore exempt; the AIM control is what keeps the prefix from
# being widened into an amnesty.
FAMILY_PREFIX = "_fabro_port"

# Package-relative POSIX paths the walk MUST reach: the two modules that own
# the seam, plus the three that reached past it before the conversion. A walk
# that misses one is mis-scoped, and those three are exactly where a
# regression would land first.
DISCOVERY_ANCHORS: tuple[str, ...] = (
    "commands/_acp_factory_capabilities.py",
    "commands/_dispatcher_preserve_reference.py",
    "commands/_dispatcher_preserve_reference_check.py",
    "commands/_fabro_port.py",
    "commands/_fabro_port_http.py",
)

# A module that is unambiguously the Dispatcher rather than the facade. If the
# exemption ever covers this, it covers everything.
AIM_ANCHOR = "commands/_dispatcher_engine.py"

_PACKAGE_RELPATH = (".claude-plugin", "scripts", "livespec_orchestrator_beads_fabro")
_FIXTURE_RELPATH = ("dev-tooling", "checks", "fixtures", "fabro_port_seam_control.py.txt")
_BINARY_NAMES = frozenset({"fabro_bin"})
_BINARY_CONSTANTS = frozenset({"fabro"})
_TRANSPORT_FUNCTIONS = frozenset({"fabro_http_request"})
_TRANSPORT_SEND = "send"
_TRANSPORT_SEND_KEYWORDS = frozenset({"method", "url"})
_SERVER_API_PREFIX = "/api/v1"
_FINDING_MESSAGE = "Fabro engine reached outside the _fabro_port facade family"
# The remedy each control failure names, kept beside the forms rather than
# wrapped into the message, so no message needs implicit concatenation.
_AIM_FIX = "the exemption must name the facade family alone"
_SEAM_FIX = "the exemption is no longer covering the seam"


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One Fabro engine invocation, with the form that recognized it."""

    relpath: str
    lineno: int
    form: str
    expression: str


def _is_binary_read(*, node: ast.AST) -> bool:
    """Whether this expression evaluates to the engine binary's path."""
    match node:
        case ast.Attribute(attr=attr):
            return attr in _BINARY_NAMES
        case ast.Name(id=name):
            return name in _BINARY_NAMES
        case ast.Constant(value=str() as value):
            return value in _BINARY_CONSTANTS
        # `str(args.fabro_bin)` and friends: a one-argument conversion of the
        # read IS the read, and both converted call sites spelled it that way.
        case ast.Call(args=[argument], keywords=[]):
            return _is_binary_read(node=argument)
        case _:
            return False


def _is_transport_call(*, node: ast.Call) -> bool:
    name = ast.unparse(node.func).rsplit(".", maxsplit=1)[-1]
    if name in _TRANSPORT_FUNCTIONS:
        return True
    keywords = {keyword.arg for keyword in node.keywords}
    return name == _TRANSPORT_SEND and keywords >= _TRANSPORT_SEND_KEYWORDS


def _finding_form(*, node: ast.AST) -> str | None:
    match node:
        case ast.List(elts=[first, *_]) | ast.Tuple(elts=[first, *_]) if _is_binary_read(
            node=first
        ):
            return FORM_BINARY_ARGV
        case ast.Call() if _is_transport_call(node=node):
            return FORM_TRANSPORT_CALL
        case ast.Constant(value=str() as value) if value.startswith(_SERVER_API_PREFIX):
            return FORM_SERVER_API_PATH
        case _:
            return None


def source_findings(*, source: str, relpath: str) -> list[Finding]:
    """Every Fabro engine invocation in one module's source."""
    tree = ast.parse(source, filename=relpath)
    findings = [
        Finding(
            relpath=relpath,
            lineno=getattr(node, "lineno", 0),
            form=form,
            expression=ast.unparse(node),
        )
        for node, form in ((node, _finding_form(node=node)) for node in ast.walk(tree))
        if form is not None
    ]
    return sorted(findings, key=lambda finding: (finding.lineno, finding.form, finding.expression))


def package_dir(*, repo_root: Path) -> Path:
    """The scanned package root."""
    return repo_root.joinpath(*_PACKAGE_RELPATH)


def fixture_path(*, repo_root: Path) -> Path:
    """The positive-control fixture carrying all three invocation forms."""
    return repo_root.joinpath(*_FIXTURE_RELPATH)


def is_family_module(*, path: Path) -> bool:
    """Whether this module IS the facade, and so may reach the engine."""
    return path.name.startswith(FAMILY_PREFIX)


def module_paths(*, root: Path) -> list[Path]:
    """Every module the scan walks under `root`.

    The walked tree is LIVE, so it can change underneath the walk. `os.walk`
    rather than `Path.rglob` because pathlib lists a directory and then opens
    it, and lets a `FileNotFoundError` from that open escape: a `__pycache__`
    removed concurrently between the two steps has taken a sibling check down
    and turned master CI red on a pure version bump. `os.walk` ignores a
    `scandir` error by default, so a vanished subtree is dropped rather than
    fatal, and `__pycache__` is pruned from the descent as well as tolerated.
    """
    paths: list[Path] = []
    for parent, dirnames, filenames in os.walk(root):
        dirnames[:] = [dirname for dirname in dirnames if dirname != "__pycache__"]
        paths.extend(Path(parent) / name for name in filenames if name.endswith(".py"))
    return sorted(paths)


def path_findings(*, paths: Iterable[Path], root: Path) -> list[Finding]:
    """Findings for an explicit file list — the shared read/parse/match path."""
    findings: list[Finding] = []
    for path in paths:
        findings.extend(
            source_findings(
                source=path.read_text(encoding="utf-8"),
                relpath=path.relative_to(root).as_posix(),
            )
        )
    return findings


def package_findings(*, repo_root: Path) -> list[Finding]:
    """Every engine invocation the facade family does not account for."""
    root = package_dir(repo_root=repo_root)
    scanned = [path for path in module_paths(root=root) if not is_family_module(path=path)]
    return path_findings(paths=scanned, root=root)


def family_findings(*, repo_root: Path) -> list[Finding]:
    """The facade family's OWN invocations — the seam, scanned unexempted."""
    root = package_dir(repo_root=repo_root)
    family = [path for path in module_paths(root=root) if is_family_module(path=path)]
    return path_findings(paths=family, root=root)


def control_failures(*, repo_root: Path) -> list[str]:
    """Why a clean scan of `repo_root` would not be trustworthy, if it would not."""
    failures: list[str] = []
    root = package_dir(repo_root=repo_root)
    discovered = {path.relative_to(root).as_posix() for path in module_paths(root=root)}
    failures.extend(
        f"discovery control: the walk of {root} did not reach {anchor}"
        for anchor in DISCOVERY_ANCHORS
        if anchor not in discovered
    )
    if is_family_module(path=root / AIM_ANCHOR):
        failures.append(f"aim control: {AIM_ANCHOR} is exempt under {FAMILY_PREFIX!r}; {_AIM_FIX}")
    seam_forms = {finding.form for finding in family_findings(repo_root=repo_root)}
    failures.extend(
        f"seam control: the exempt family carries no {form} invocation; {_SEAM_FIX}"
        for form in FORMS
        if form not in seam_forms
    )
    failures.extend(_matcher_failures(repo_root=repo_root))
    return failures


def _matcher_failures(*, repo_root: Path) -> list[str]:
    fixture = fixture_path(repo_root=repo_root)
    if not fixture.is_file():
        return [f"matcher control: the positive-control fixture is missing at {fixture}"]
    found = {finding.form for finding in path_findings(paths=[fixture], root=fixture.parent)}
    return [
        f"matcher control: no {form} invocation was found in {fixture}"
        for form in FORMS
        if form not in found
    ]


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("fabro_port_seam")
    repo_root = Path.cwd()
    failures = control_failures(repo_root=repo_root)
    for failure in failures:
        log.error(
            "positive control failed; this scan cannot report a trustworthy absence",
            detail=failure,
        )
    findings = package_findings(repo_root=repo_root)
    for finding in findings:
        log.error(
            _FINDING_MESSAGE,
            path=finding.relpath,
            line=finding.lineno,
            form=finding.form,
            expression=finding.expression,
        )
    return 1 if failures or findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
