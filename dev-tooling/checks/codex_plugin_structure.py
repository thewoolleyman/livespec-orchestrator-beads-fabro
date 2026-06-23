# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""codex_plugin_structure — structural gate for the Codex cross-runtime surface.

Validates the orchestrator plugin's Codex surface, the cross-runtime
sibling of its Claude `.claude-plugin/` surface (per
livespec/SPECIFICATION/constraints.md §"Codex support" — Codex adapters
are thin runtime bindings over the same wrapper CLIs, beads tenant
semantics, and consent rules as the Claude skills, and MUST NOT copy
Claude-specific SKILL.md bodies). The orchestrator's payload (`scripts/`,
the Claude `skills/`) lives INSIDE `.claude-plugin/`; the Codex bindings
are SEPARATE, under a NESTED `.claude-plugin/.codex-plugin/skills/` tree
the repo-root `.agents/plugins/marketplace.json` catalog points at via the
`./.claude-plugin` plugin source (the install flattens that dir, so the
cache root carries `scripts/` directly — empirically verified: `codex
plugin add` accepts the nested skills path and `codex exec` discovers the
skill).

SCOPE — the four THIN ops only (P3a). Only the four wrapper-backed ops
(next, list-work-items, detect-impl-gaps, orchestrate) ship a Codex
binding here; each dispatches to its `scripts/bin/<op>.py` reference
wrapper. The five HEAVYWEIGHT authored ops (capture-work-item,
capture-impl-gaps, capture-spec-drift, implement, groom) carry inline
orchestration in their Claude SKILL.md with NO single CLI wrapper, so a
faithful Codex binding requires extracting that orchestration to a
shared harness-neutral prose layer (which the orchestrator does not have
today) AND a GOVERNED spec change — that is the separate P3b effort. To
keep that gap VISIBLE rather than silent, this check enumerates the five
pending ops explicitly (`_PENDING_CODEX_OPS`) and ASSERTS their Codex
skill dirs are ABSENT, so an improvised partial binding cannot land
without flipping the op out of the pending set here. P3b flips each op
from pending to present.

NO Codex hooks are shipped (deliberate): the orchestrator's Claude
surface ships no hooks, so a Codex-only guard would be asymmetric; the
family commit-refuse hook + branch protection are the real git-footgun
backstops; and constraints.md gates the CLAIM of Codex support on manual
verification, not on shipping a guard. So `.codex-plugin/plugin.json`
declares NO `hooks` key and there is no `.codex-plugin/hooks/` dir — and
this check ENFORCES that absence.

Assertions:

1. `.agents/plugins/marketplace.json` parses as JSON; top-level `name` is
   `livespec-orchestrator-beads-fabro`; exactly one plugin entry named
   `livespec-orchestrator-beads-fabro` whose `source` is
   `{"source":"local","path":"./.claude-plugin"}` and whose `description`
   duplicates the Codex manifest's verbatim.
2. `.claude-plugin/.codex-plugin/plugin.json` parses as JSON; `name` is
   `livespec-orchestrator-beads-fabro`; `version` equals the Claude
   `.claude-plugin/plugin.json` version (single artifact, versions in
   lockstep); `skills` is `./.codex-plugin/skills/`; `description` equals
   the Claude `plugin.json` description; there is NO `hooks` key.
3. Each of the four present ops ships a `SKILL.md` under
   `.claude-plugin/.codex-plugin/skills/<op>/` whose `---`-fenced
   frontmatter `name` matches its directory, carries a non-empty
   `description`, and carries NO `allowed-tools` key; no extra skill dirs
   exist; and each of the five pending ops has NO skill dir.
4. Body rules in every present SKILL.md: the body MUST carry the Codex
   core-resolution invocation `codex plugin list --json -m
   livespec-orchestrator-beads-fabro` and the `$PLUGIN_ROOT` resolution
   variable, MUST NOT carry a live `${CLAUDE_PLUGIN_ROOT}` token, and MUST
   self-invoke its `scripts/bin/<op>.py` wrapper.
5. Wrapper-invocation rules in every present SKILL.md: any fenced line
   invoking a `bin/<name>.py` wrapper MUST use `$PLUGIN_ROOT`, MUST NOT
   use `uv run`, MUST NOT use a literal `.claude-plugin/scripts` path, and
   MUST NOT use the `CLAUDE_PLUGIN_ROOT` token.

Diagnostics flow through structlog (JSON to stderr) — the only output
surface the `no_write_direct` ban permits for an enforcement script;
structlog is imported from the installed `livespec_dev_tooling` package's
vendored copy. Exit 0 when every assertion holds; exit 1 otherwise.
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
# `sys.path` here. The file-level pyright pragma above silences the
# untyped-structlog diagnostics this import would otherwise raise.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
if str(_DT_VENDOR) not in sys.path:
    sys.path.insert(0, str(_DT_VENDOR))

import structlog  # noqa: E402

__all__: list[str] = ["main"]

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_MARKETPLACE = _REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
_CLAUDE_DIR = _REPO_ROOT / ".claude-plugin"
_CLAUDE_MANIFEST = _CLAUDE_DIR / "plugin.json"
_CODEX_DIR = _CLAUDE_DIR / ".codex-plugin"
_CODEX_MANIFEST = _CODEX_DIR / "plugin.json"
_SKILLS_DIR = _CODEX_DIR / "skills"

# The four PRESENT (thin, wrapper-backed) ops each dispatch to a
# `scripts/bin/<op>.py` CLI. These are the only Codex bindings shipped today.
_PRESENT_OPS: dict[str, str] = {
    "next": "next.py",
    "list-work-items": "list_work_items.py",
    "detect-impl-gaps": "detect_impl_gaps.py",
    "orchestrate": "orchestrate.py",
}
# The five HEAVYWEIGHT authored ops have NO single CLI wrapper; a Codex
# binding requires the P3b shared-prose extraction + a governed spec change.
# Enumerated here so their absence is VISIBLE (asserted), never silent — P3b
# flips each from this set into `_PRESENT_OPS`.
_PENDING_CODEX_OPS = frozenset(
    {
        "capture-work-item",
        "capture-impl-gaps",
        "capture-spec-drift",
        "implement",
        "groom",
    }
)

_EXPECTED_SOURCE = {"source": "local", "path": "./.claude-plugin"}
_EXPECTED_SKILLS_PATH = "./.codex-plugin/skills/"
_CODEX_RESOLUTION_SNIPPET = f"codex plugin list --json -m {_PLUGIN_NAME}"
_PLUGIN_ROOT_VAR = "$PLUGIN_ROOT"

_WRAPPER_INVOCATION_RE = re.compile(r"bin/[a-z_]+\.py\b")
_FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)
_FRONTMATTER_DESCRIPTION_RE = re.compile(r"^description:\s*(\S.*?)\s*$", re.MULTILINE)
# Assembled from parts so this checker file itself never contains the literal
# placeholder token it bans.
_DRIVER_ROOT_TOKEN = "${CLAUDE_PLUGIN" + "_ROOT}"


def _frontmatter_block(*, text: str) -> str | None:
    """Return the `---`-fenced frontmatter block, or None if absent/malformed.

    The block MUST be the first thing in the file: an opening `---` line,
    body lines, then a closing `---` line.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[1:idx])
    return None


def _read_json(*, path: Path) -> tuple[Any, str | None]:
    """Parse a JSON file; return (parsed_or_None, error_message_or_None)."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, str(exc)


def _str_field(*, parsed: Any, key: str) -> str | None:
    """Return `parsed[key]` if `parsed` is a dict and the value is a str, else None."""
    if isinstance(parsed, dict):
        value = cast("dict[str, Any]", parsed).get(key)
        if isinstance(value, str):
            return value
    return None


def _claude_meta() -> tuple[str | None, str | None]:
    """The Claude `.claude-plugin/plugin.json` (description, version) — the source of truth.

    The Codex manifest's description and version are kept in lockstep with these.
    """
    parsed, _ = _read_json(path=_CLAUDE_MANIFEST)
    return _str_field(parsed=parsed, key="description"), _str_field(parsed=parsed, key="version")


def _marketplace_violations(*, codex_description: str | None) -> list[str]:
    """Validate the repo-root marketplace catalog."""
    out: list[str] = []
    marketplace, err = _read_json(path=_MARKETPLACE)
    if err is not None or not isinstance(marketplace, dict):
        return [f".agents/plugins/marketplace.json unreadable/invalid: {err}"]
    marketplace_dict = cast("dict[str, Any]", marketplace)
    if marketplace_dict.get("name") != _PLUGIN_NAME:
        got_name = marketplace_dict.get("name")
        out.append(f"marketplace.json name MUST be {_PLUGIN_NAME!r}; got {got_name!r}")
    entries = marketplace_dict.get("plugins", [])
    if not isinstance(entries, list) or len(entries) != 1:
        count = len(entries) if isinstance(entries, list) else "non-list"
        out.append(f"marketplace.json MUST list exactly one plugin; got {count}")
        return out
    entry = cast("dict[str, Any]", entries[0]) if isinstance(entries[0], dict) else {}
    if entry.get("name") != _PLUGIN_NAME:
        out.append(f"marketplace entry name MUST be {_PLUGIN_NAME!r}; got {entry.get('name')!r}")
    if entry.get("source") != _EXPECTED_SOURCE:
        got = entry.get("source")
        out.append(f"marketplace entry source MUST be {_EXPECTED_SOURCE!r}; got {got!r}")
    if codex_description is not None and entry.get("description") != codex_description:
        out.append("marketplace entry description MUST duplicate the Codex plugin.json's verbatim")
    return out


def _manifest_violations(
    *, claude_description: str | None, claude_version: str | None
) -> list[str]:
    """Validate the Codex plugin manifest against the Claude manifest + layout."""
    out: list[str] = []
    plugin, err = _read_json(path=_CODEX_MANIFEST)
    if err is not None or not isinstance(plugin, dict):
        return [f".claude-plugin/.codex-plugin/plugin.json unreadable/invalid: {err}"]
    plugin_dict = cast("dict[str, Any]", plugin)
    if plugin_dict.get("name") != _PLUGIN_NAME:
        out.append(f"plugin.json name MUST be {_PLUGIN_NAME!r}; got {plugin_dict.get('name')!r}")
    if claude_version is not None and plugin_dict.get("version") != claude_version:
        got_version = plugin_dict.get("version")
        out.append(f"plugin.json version MUST equal Claude {claude_version!r}; got {got_version!r}")
    if plugin_dict.get("skills") != _EXPECTED_SKILLS_PATH:
        got_skills = plugin_dict.get("skills")
        out.append(f"plugin.json skills MUST be {_EXPECTED_SKILLS_PATH!r}; got {got_skills!r}")
    if claude_description is not None and plugin_dict.get("description") != claude_description:
        out.append("plugin.json description MUST equal the Claude plugin.json description verbatim")
    if "hooks" in plugin_dict:
        out.append("plugin.json MUST NOT carry a 'hooks' key (the Codex surface ships no hooks)")
    return out


def _hooks_dir_violations() -> list[str]:
    """The no-guard contract also forbids a `.codex-plugin/hooks/` directory."""
    if (_CODEX_DIR / "hooks").exists():
        return [".codex-plugin/hooks/ MUST NOT exist (the Codex surface ships no hooks)"]
    return []


def _skill_set_violations() -> list[str]:
    out: list[str] = []
    if not _SKILLS_DIR.is_dir():
        return [f"missing skills directory: {_SKILLS_DIR.relative_to(_REPO_ROOT)}/"]
    found = {p.name for p in _SKILLS_DIR.iterdir() if p.is_dir()}
    for missing in sorted(set(_PRESENT_OPS) - found):
        out.append(f"missing skill directory: .codex-plugin/skills/{missing}/")
    # A pending op's dir must be ABSENT — keep the P3b gap visible, not
    # papered over by an improvised partial binding.
    for premature in sorted(_PENDING_CODEX_OPS & found):
        out.append(f"P3b-pending heavyweight op must NOT ship a skill dir yet: {premature}")
    for extra in sorted(found - set(_PRESENT_OPS) - _PENDING_CODEX_OPS):
        out.append(f"unexpected skill directory: .codex-plugin/skills/{extra}/")
    for name in sorted(set(_PRESENT_OPS) & found):
        out.extend(_one_skill_violations(name=name))
    return out


def _one_skill_violations(*, name: str) -> list[str]:
    """Frontmatter + body + invocation rules for one present skill directory."""
    skill_md = _SKILLS_DIR / name / "SKILL.md"
    if not skill_md.is_file():
        return [f"missing .codex-plugin/skills/{name}/SKILL.md"]
    text = skill_md.read_text(encoding="utf-8")
    out = _frontmatter_violations(name=name, text=text)
    out.extend(_binding_body_violations(name=name, text=text))
    out.extend(_invocation_violations(name=name, skill_md=skill_md))
    return out


def _frontmatter_violations(*, name: str, text: str) -> list[str]:
    out: list[str] = []
    where = f".codex-plugin/skills/{name}/SKILL.md"
    frontmatter = _frontmatter_block(text=text)
    if frontmatter is None:
        return [f"{where} MUST open with a `---`-fenced frontmatter block"]
    name_match = _FRONTMATTER_NAME_RE.search(frontmatter)
    if name_match is None or name_match.group(1) != name:
        got = None if name_match is None else name_match.group(1)
        out.append(f"{where} frontmatter name MUST be {name!r}; got {got!r}")
    desc_match = _FRONTMATTER_DESCRIPTION_RE.search(frontmatter)
    if desc_match is None or not desc_match.group(1).strip():
        out.append(f"{where} frontmatter description MUST be non-empty")
    if "allowed-tools" in frontmatter:
        out.append(f"{where} frontmatter MUST NOT carry an 'allowed-tools' key")
    return out


def _binding_body_violations(*, name: str, text: str) -> list[str]:
    """Resolution-snippet presence, the live-token ban, and the wrapper self-invocation."""
    out: list[str] = []
    where = f".codex-plugin/skills/{name}/SKILL.md"
    if _CODEX_RESOLUTION_SNIPPET not in text:
        out.append(f"{where}: body MUST carry the resolution snippet {_CODEX_RESOLUTION_SNIPPET!r}")
    if _PLUGIN_ROOT_VAR not in text:
        out.append(f"{where}: body MUST carry the {_PLUGIN_ROOT_VAR} resolution variable")
    if _DRIVER_ROOT_TOKEN in text:
        out.append(f"{where}: body MUST NOT carry a live {_DRIVER_ROOT_TOKEN} token")
    wrapper_script = _PRESENT_OPS[name]
    if f"scripts/bin/{wrapper_script}" not in text:
        out.append(f"{where}: body MUST invoke scripts/bin/{wrapper_script}")
    return out


def _invocation_violations(*, name: str, skill_md: Path) -> list[str]:
    """Every fenced `bin/<name>.py` invocation must use the $PLUGIN_ROOT idiom."""
    out: list[str] = []
    in_fence = False
    for line_no, raw in enumerate(skill_md.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence or _WRAPPER_INVOCATION_RE.search(stripped) is None:
            continue
        where = f".codex-plugin/skills/{name}/SKILL.md:{line_no}"
        if "uv run" in stripped:
            out.append(f"{where}: fenced invocation uses 'uv run'")
        if ".claude-plugin/scripts" in stripped:
            out.append(f"{where}: fenced invocation uses a literal .claude-plugin/scripts path")
        if "CLAUDE_PLUGIN_ROOT" in stripped:
            out.append(f"{where}: fenced invocation uses the Claude plugin-root token")
        if _PLUGIN_ROOT_VAR not in stripped:
            out.append(f"{where}: fenced invocation MUST use {_PLUGIN_ROOT_VAR}")
    return out


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("codex_plugin_structure")
    # Surface the P3b gap on every run so the four-op scope stays visible
    # (constraints.md §"Codex support" L122 gates the CLAIM of Codex support
    # on the full surface; the heavyweight ops land via P3b).
    log.info(
        "codex surface scope (P3a)",
        present_ops=sorted(_PRESENT_OPS),
        pending_ops_p3b=sorted(_PENDING_CODEX_OPS),
    )
    claude_description, claude_version = _claude_meta()
    codex_plugin, _ = _read_json(path=_CODEX_MANIFEST)
    codex_description = _str_field(parsed=codex_plugin, key="description")
    violations: list[str] = []
    violations.extend(_marketplace_violations(codex_description=codex_description))
    violations.extend(
        _manifest_violations(claude_description=claude_description, claude_version=claude_version)
    )
    violations.extend(_hooks_dir_violations())
    violations.extend(_skill_set_violations())
    if not violations:
        return 0
    for violation in violations:
        log.error("codex-plugin-structure violation", detail=violation)
    return 1


# The shebang-less module is invoked via `just check-codex-plugin-structure`
# (`uv run python dev-tooling/checks/codex_plugin_structure.py`); the guard
# keeps the exit code propagating to the shell.
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
