# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""pi_plugin_structure — structural gate for the pi cross-runtime surface.

Validates the orchestrator plugin's pi surface, the third sibling of its Claude
`.claude-plugin/skills/` bindings and its Codex `.claude-plugin/.codex-plugin/`
bindings (per this repository's `SPECIFICATION/contracts.md`). The payload
(`scripts/`, `prose/`) has ONE home under `.claude-plugin/`; the pi bindings sit
beside it under `.claude-plugin/.pi-plugin/skills/`, named by the repo-root
`package.json` pi manifest.

The shared `check-skill-invocation-paths` Verifier guards the analogous
invariants for the CLAUDE bindings and is scoped to `.claude-plugin/skills/`, so
it VACUOUSLY SKIPS this tree — it returns 0 having inspected nothing. This check
is the pi analogue, so the invariants are enforced against the tree that
actually ships to pi.

The operation set is DERIVED, never enumerated here: every directory under
`.claude-plugin/skills/` is an operation this plugin ships, and each one MUST
have exactly one pi binding named `livespec-orchestrator-beads-fabro-<op>`. An
operation added or retired on the Claude side therefore changes what this check
demands in the same act, rather than through a second list that can silently
fall behind. Each operation's BACKING is derived the same way: an operation with
a `prose/<op>.md` artifact is prose-backed and its binding MUST read that prose;
an operation without one is wrapper-backed and its binding MUST self-invoke its
`scripts/bin/<op>.py` wrapper.

What it asserts, and why each one is load-bearing:

- **The pi manifest.** The repo-root `package.json` carries the `pi-package`
  keyword and a `pi` block naming the bindings directory, which must exist — a
  manifest naming a directory that is not there loads nothing and reports
  nothing. It declares NO `extensions`: the sanctioned pi footgun guard is the
  pi Driver's, and a second registration of the same handler would double-guard
  the same tool calls without adding a control.
- **One binding per operation, and only those.** A missing binding is a silently
  absent command; an extra one is a surface this plugin never contracted to
  expose.
- **Frontmatter conformance.** pi refuses to load a skill with no description
  and warns on a name that breaks the Agent Skills name rules. Both failures are
  quiet at runtime, so they are loud here. The directory name must equal the
  frontmatter name: pi tolerates a mismatch, the Agent Skills standard does not.
- **Thin-binding bodies.** A binding delegates plugin-root resolution to the one
  shared resolver rather than restating the algorithm inline, carries no live
  Claude plugin-root token, and points at no `skills/` tree of another runtime.
- **Canonical wrapper invocation.** A fenced line invoking a `bin/<name>.py`
  wrapper must go through `$PLUGIN_ROOT`, never `uv run` (the installed package
  has no project to resolve) and never a hard-coded plugin-directory literal.

Diagnostics flow through structlog (JSON to stderr) — the only output surface
the `no_write_direct` ban permits for an enforcement script. Exit 0 when every
assertion holds; exit 1 otherwise.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
_SCRIPTS_VENDOR = _SCRIPTS / "_vendor"
for _path in (_SCRIPTS, _SCRIPTS_VENDOR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script
# (per the `no_write_direct` ban on direct `sys.stderr.write`). It is not
# vendored in this repo's own tree, so it is imported from the installed
# `livespec_dev_tooling` package's vendored copy, whose path is added to
# `sys.path` here.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
# APPEND, never insert at the front: since livespec-dev-tooling v1.90.0 that
# `_vendor` also carries a PARTIAL `livespec_runtime` (the github_budget
# modules only, no `work_items`), and putting it ahead of this repo's own
# `_vendor` shadowed the full copy every plugin module imports, so every
# check in this directory died on `No module named
# 'livespec_runtime.work_items'` (livespec-dev-tooling-8o8e.24 is the
# two-copies class). Appending keeps `structlog` resolvable while this
# repo's full vendored runtime keeps precedence.
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

import structlog  # noqa: E402

__all__: list[str] = ["main", "violations"]

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_EXPECTED_SKILLS_PATH = "./.claude-plugin/.pi-plugin/skills"
_RESOLVER_RELATIVE = "lib/resolve-plugin-root.sh"
_PLUGIN_ROOT_VAR = "$PLUGIN_ROOT"

_NAME_RULES = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_NAME_LIMIT = 64
_FENCE = "```"
_WRAPPER_INVOCATION_RE = re.compile(r"bin/[a-z_]+\.py\b")
_FRONTMATTER_FIELD_RE = re.compile(
    r"""^([a-z-]+):\s*(?:(["'])(.*?)\2|((?=\S)(?!.*:\s).*?))\s*$""",
    re.MULTILINE,
)
# Assembled from parts so this checker file itself never contains the literal
# placeholder token it bans.
_CLAUDE_ROOT_TOKEN = "${CLAUDE_PLUGIN" + "_ROOT}"
_OTHER_RUNTIME_SKILL_TREES = (".claude-plugin/skills", ".codex-plugin/skills")


def _pi_dir(*, root: Path) -> Path:
    return root / ".claude-plugin" / ".pi-plugin"


def _frontmatter(*, text: str) -> dict[str, str]:
    """The `key: value` pairs of a leading `---` fenced block.

    Deliberately not a YAML parser: pi SKILL.md frontmatter in this package is
    flat scalars only, and depending on a YAML library for a dozen files would
    be a new dependency guarding nothing.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        matched = _FRONTMATTER_FIELD_RE.match(line)
        if matched:
            fields[matched.group(1)] = matched.group(3) or matched.group(4)
    return fields


def _fenced_invocations(*, text: str) -> list[str]:
    """Stripped in-fence lines that invoke a `bin/<name>.py` wrapper.

    Prose references OUTSIDE fences are narration, not executable command lines,
    and are never gathered — the same fenced-versus-prose distinction the shared
    Claude-side Verifier draws.
    """
    gathered: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_FENCE):
            in_fence = not in_fence
            continue
        if in_fence and _WRAPPER_INVOCATION_RE.search(stripped):
            gathered.append(stripped)
    return gathered


def operations(*, root: Path) -> list[str]:
    """The operations this plugin ships, derived from its Claude bindings."""
    claude_skills = root / ".claude-plugin" / "skills"
    if not claude_skills.is_dir():
        return []
    return sorted(entry.name for entry in claude_skills.iterdir() if entry.is_dir())


def wrapper_for(*, root: Path, operation: str) -> str | None:
    """The wrapper backing an operation, or None when it is prose-backed."""
    if (root / ".claude-plugin" / "prose" / f"{operation}.md").is_file():
        return None
    return f"{operation.replace('-', '_')}.py"


def _reference_violations(*, path: Path, text: str, root: Path, operation: str) -> list[str]:
    """Violations of what a binding body must (and must not) point at."""
    found: list[str] = []
    if _RESOLVER_RELATIVE not in text:
        found.append(f"{path}: does not delegate plugin-root resolution to {_RESOLVER_RELATIVE}")
    if _PLUGIN_ROOT_VAR not in text:
        found.append(f"{path}: carries no {_PLUGIN_ROOT_VAR} resolution variable")
    if _CLAUDE_ROOT_TOKEN in text:
        found.append(f"{path}: carries a live Claude plugin-root token")
    found.extend(
        f"{path}: references another runtime's bindings tree {tree}"
        for tree in _OTHER_RUNTIME_SKILL_TREES
        if tree in text
    )
    wrapper = wrapper_for(root=root, operation=operation)
    if wrapper is None:
        if f"prose/{operation}.md" not in text:
            found.append(f"{path}: prose-backed operation does not read prose/{operation}.md")
    elif f"scripts/bin/{wrapper}" not in text:
        found.append(f"{path}: wrapper-backed operation does not invoke scripts/bin/{wrapper}")
    return found


def _invocation_violations(*, path: Path, text: str) -> list[str]:
    """Violations of how a fenced wrapper invocation is written."""
    found: list[str] = []
    for command in _fenced_invocations(text=text):
        if "uv run" in command:
            found.append(f"{path}: fenced invocation uses `uv run`: {command}")
        elif ".claude-plugin/scripts" in command:
            found.append(
                f"{path}: fenced invocation hard-codes a plugin-directory literal: {command}"
            )
        elif _PLUGIN_ROOT_VAR not in command:
            found.append(f"{path}: fenced invocation lacks the {_PLUGIN_ROOT_VAR} token: {command}")
    return found


def skill_violations(*, root: Path, operation: str) -> list[str]:
    name = f"{_PLUGIN_NAME}-{operation}"
    path = _pi_dir(root=root) / "skills" / name / "SKILL.md"
    if not path.is_file():
        return [f"{path}: missing pi binding for operation '{operation}'"]
    text = path.read_text(encoding="utf-8")
    found: list[str] = []
    fields = _frontmatter(text=text)
    declared = fields.get("name", "")
    if declared != name:
        found.append(f"{path}: frontmatter name is {declared!r}, expected {name!r}")
    if not fields.get("description"):
        found.append(f"{path}: frontmatter carries no description (pi will not load the skill)")
    if not fields.get("allowed-tools"):
        found.append(f"{path}: frontmatter declares no allowed-tools")
    if not _NAME_RULES.match(declared) or len(declared) > _NAME_LIMIT:
        found.append(f"{path}: name {declared!r} breaks the Agent Skills name rules")
    found.extend(_reference_violations(path=path, text=text, root=root, operation=operation))
    found.extend(_invocation_violations(path=path, text=text))
    return found


def manifest_violations(*, root: Path) -> list[str]:
    path = root / "package.json"
    if not path.is_file():
        return [f"{path}: missing pi package manifest"]
    try:
        manifest = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
    except ValueError as invalid:
        return [f"{path}: not valid JSON: {invalid}"]
    found: list[str] = []
    if manifest.get("name") != _PLUGIN_NAME:
        found.append(f"{path}: name is {manifest.get('name')!r}, expected {_PLUGIN_NAME!r}")
    keywords = manifest.get("keywords")
    if not isinstance(keywords, list) or "pi-package" not in keywords:
        found.append(f"{path}: keywords must include 'pi-package'")
    block = manifest.get("pi")
    if not isinstance(block, dict):
        return [*found, f"{path}: carries no `pi` manifest block"]
    pi_block = cast("dict[str, Any]", block)
    if "extensions" in pi_block:
        found.append(
            f"{path}: declares pi.extensions — the pi footgun guard belongs to the pi Driver"
        )
    declared = pi_block.get("skills")
    if declared != [_EXPECTED_SKILLS_PATH]:
        found.append(f"{path}: pi.skills is {declared!r}, expected {[_EXPECTED_SKILLS_PATH]!r}")
    elif not (root / _EXPECTED_SKILLS_PATH).is_dir():
        found.append(f"{path}: pi.skills names {_EXPECTED_SKILLS_PATH}, which does not exist")
    return found


def resolver_violations(*, root: Path) -> list[str]:
    path = _pi_dir(root=root) / _RESOLVER_RELATIVE
    if not path.is_file():
        return [f"{path}: missing the shared plugin-root resolver"]
    if not path.stat().st_mode & 0o111:
        return [f"{path}: is not executable"]
    return []


def undeclared_violations(*, root: Path, expected: set[str]) -> list[str]:
    skills_root = _pi_dir(root=root) / "skills"
    if not skills_root.is_dir():
        return [f"{skills_root}: missing pi bindings tree"]
    return [
        f"{entry}: undeclared pi binding — the surface is one binding per shipped operation"
        for entry in sorted(skills_root.iterdir())
        if entry.is_dir() and entry.name not in expected
    ]


def violations(*, root: Path) -> list[str]:
    shipped = operations(root=root)
    if not shipped:
        return [f"{root}: no operations found under .claude-plugin/skills/"]
    found: list[str] = []
    for operation in shipped:
        found.extend(skill_violations(root=root, operation=operation))
    found.extend(
        undeclared_violations(root=root, expected={f"{_PLUGIN_NAME}-{op}" for op in shipped})
    )
    found.extend(resolver_violations(root=root))
    found.extend(manifest_violations(root=root))
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
    log = structlog.get_logger("pi_plugin_structure")
    shipped = operations(root=_REPO_ROOT)
    log.info(
        "pi surface scope",
        operations=shipped,
        prose_backed=[op for op in shipped if wrapper_for(root=_REPO_ROOT, operation=op) is None],
    )
    found = violations(root=_REPO_ROOT)
    if not found:
        return 0
    for violation in found:
        log.error("pi-plugin-structure violation", detail=violation)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
