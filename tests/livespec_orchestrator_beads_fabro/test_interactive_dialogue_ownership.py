"""Zero-dependency guard for `## Interactive dialogue ownership (orchestrator-side)`.

The contract (SPECIFICATION/contracts.md) makes this orchestrator the OWNER of
the interactive gap/drift consent dialogue: the plugin ships its own interactive
front-ends, and those front-ends are orchestrator-INTERNAL — the
`livespec-driver-claude` Driver does not depend on them and they MUST NOT call
back into the Driver. Invoking a core operation (e.g. the
`/livespec:propose-change` cross-boundary handoff) is permitted: that is core's
surface, which the Driver merely binds. What is forbidden is a dependency on the
Driver PLUGIN itself.

This module is the real test the heading-coverage registry maps to. It exercises
the load-bearing half that is verifiable ON THE ORCHESTRATOR SIDE:

1. Every consent-dialogue front-end skill ships its own orchestrator prose
   (`${CLAUDE_PLUGIN_ROOT}/prose/<op>.md`) — the affirmative "ships with the
   orchestrator" property.
2. No consent-dialogue front-end skill names the `livespec-driver-claude` Driver
   plugin.
3. The orchestrator's Python package imports no Driver module — the literal
   "no Driver import" property, scanned via AST so comments and string literals
   cannot produce a false positive.

(Core's complementary half — core's contract names only the three orchestrator
CLIs and no front-end — is asserted on the core side by the livespec
`test_livespec_config` orchestrator-three-CLIs round-trip.)
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro"
_SKILLS_DIR = _REPO_ROOT / ".claude-plugin" / "skills"

# The interactive per-finding consent front-ends owned by this orchestrator
# (per SPECIFICATION/contracts.md, the store-write consent discipline).
_CONSENT_DIALOGUE_SKILLS: tuple[str, ...] = (
    "capture-impl-gaps",
    "capture-spec-drift",
    "capture-work-item",
    "groom",
)

# The Driver plugin these front-ends MUST NOT depend on: the kebab plugin name
# is forbidden in front-end skill text; the snake import root is forbidden both
# in skill text and as a Python import target.
_DRIVER_PLUGIN_NAME = "livespec-driver-claude"
_DRIVER_IMPORT_ROOT = "livespec_driver_claude"


def _skill_md(*, op: str) -> Path:
    return _SKILLS_DIR / op / "SKILL.md"


def _imported_roots(*, source: str) -> set[str]:
    """Top-level package names of every absolute import in `source`, via AST.

    `import a.b` -> {"a"}; `from a.b import c` -> {"a"}; relative imports
    (`from . import x`) contribute nothing. Comments and string literals are
    invisible to the parser, so neither can be mistaken for an import.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots


def _driver_import_offenders(*, package_dir: Path) -> list[str]:
    """Names of `*.py` files under `package_dir` whose AST imports the Driver root."""
    offenders: list[str] = []
    for py in sorted(package_dir.rglob("*.py")):
        if _DRIVER_IMPORT_ROOT in _imported_roots(source=py.read_text(encoding="utf-8")):
            offenders.append(py.name)
    return offenders


def test_consent_dialogue_skills_exist() -> None:
    """The enumerated consent-dialogue front-ends are present as skills.

    Without this guard the other tests would pass vacuously if a skill were
    renamed or removed out from under the enumeration.
    """
    for op in _CONSENT_DIALOGUE_SKILLS:
        assert _skill_md(op=op).is_file(), f"missing consent-dialogue skill: {op}"


def test_consent_dialogue_skills_ship_orchestrator_prose() -> None:
    """Each front-end reads its OWN plugin prose — it ships with the orchestrator."""
    for op in _CONSENT_DIALOGUE_SKILLS:
        body = _skill_md(op=op).read_text(encoding="utf-8")
        marker = f"prose/{op}.md"
        assert marker in body, f"{op} SKILL.md does not read its own prose ({marker})"


def test_consent_dialogue_skills_carry_no_driver_dependency() -> None:
    """No front-end skill names the livespec-driver-claude Driver plugin.

    Invoking core operations (e.g. /livespec:propose-change) is permitted — that
    is core's surface, which the Driver merely binds. Naming the Driver PLUGIN
    itself is the forbidden dependency.
    """
    for op in _CONSENT_DIALOGUE_SKILLS:
        body = _skill_md(op=op).read_text(encoding="utf-8")
        assert (
            _DRIVER_PLUGIN_NAME not in body
        ), f"{op} SKILL.md references the Driver plugin {_DRIVER_PLUGIN_NAME!r}"
        assert (
            _DRIVER_IMPORT_ROOT not in body
        ), f"{op} SKILL.md references the Driver import root {_DRIVER_IMPORT_ROOT!r}"


def test_orchestrator_package_imports_no_driver_module() -> None:
    """The orchestrator package carries zero import edges into the Driver plugin."""
    offenders = _driver_import_offenders(package_dir=_PACKAGE_DIR)
    assert not offenders, f"orchestrator modules import the Driver: {offenders}"


def test_driver_import_detector_flags_a_synthetic_importer(tmp_path: Path) -> None:
    """The detector flags a module that DOES import the Driver, and spares one that does not.

    Exercises both arms of the scan so the guard's offending path is proven to
    fire — a guard that can never report a violation is no guard at all.
    """
    _ = (tmp_path / "offender.py").write_text(
        "from livespec_driver_claude.bindings import resolve\n", encoding="utf-8"
    )
    _ = (tmp_path / "clean.py").write_text("from livespec.io import fs\n", encoding="utf-8")
    assert _driver_import_offenders(package_dir=tmp_path) == ["offender.py"]
