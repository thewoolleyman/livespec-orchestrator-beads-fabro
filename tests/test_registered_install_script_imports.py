"""A primary-run script imports from the REGISTERED install only what that build ships.

`dev-tooling/dod-preflight.sh` runs from the governed repository's primary
checkout, which fast-forwards with master, but it imports the package from the
orchestrator build that repository has REGISTERED in Claude Code's install
registry, which moves only when a release is adopted. The two are skewed by
design. On 2026-11-14, PR #5270 added an unguarded import of
`_dispatcher_dod_judgement_preflight_reuse` (a module new in that same PR) to
the script. The registered v0.328.0 build did not carry it, so every fleet
launch's preflight raised `ImportError`, which the script reports as exit 1, a
REFUSAL, and every launch stopped until the change was reverted (#5277).

The control is structural. It finds every `dev-tooling/` script that loads the
package from the registered install (it reads `installed_plugins.json`), parses
each of its Python heredocs, and requires every package import that does NOT
sit in a `try:` body with an `ImportError` handler to name a member of the
REGISTERED-BUILD FLOOR below. A guarded import is the script's declared
fallback for a build that predates the module, so it may name anything.

Why a pinned floor rather than a release tag read from git: CI's pytest job
checks out at depth 1 with no tags, so a history-derived reference would have
nothing to compare against in exactly the job that must refuse the import. The
floor moves only by a reviewed edit to this file, made when the fleet's
registered build moves, and the last test below keeps it honest against this
tree.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEV_TOOLING = _REPO_ROOT / "dev-tooling"
_PACKAGE_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
_PACKAGE = "livespec_orchestrator_beads_fabro"
_REGISTRY_MARKER = "installed_plugins.json"
_IMPORT_ERRORS = frozenset({"ImportError", "ModuleNotFoundError"})
_HEREDOC = re.compile(r"<<'(?P<tag>[A-Z_]+)'[^\n]*\n(?P<body>.*?)\n(?P=tag)\n", re.DOTALL)

# Every (module, name) below was verified present in v0.328.0 (build
# c1f8445faf3b), the orchestrator build every primary repository registered on
# 2026-11-14. Add an entry ONLY after confirming the oldest build the fleet still
# registers ships it; otherwise guard the import with an `ImportError` fallback.
_C = f"{_PACKAGE}.commands"
_REGISTERED_BUILD_FLOOR = frozenset(
    {
        (f"{_PACKAGE}._store_comments", "append_work_item_comment"),
        (f"{_PACKAGE}._store_comments", "read_work_item_comments"),
        (f"{_PACKAGE}.store", "materialize_work_items"),
        (f"{_PACKAGE}.store", "read_work_items"),
        (f"{_C}._acp_candidate_schema", "AcpCandidate"),
        (f"{_C}._acp_node_adapters", "parse_adapter_string"),
        (f"{_C}._config", "dispatcher_block"),
        (f"{_C}._dispatcher_definition_of_done", "definition_of_done"),
        (f"{_C}._dispatcher_definition_of_done_findings", "definition_of_done_findings"),
        (f"{_C}._dispatcher_dod_gate_candidates", "dod_gate_candidates"),
        (f"{_C}._dispatcher_dod_judgement", "judgement_subject"),
        (f"{_C}._dispatcher_dod_judgement", "judgement_subject_digest"),
        (f"{_C}._dispatcher_dod_judgement", "parse_judgement_reply"),
        (f"{_C}._dispatcher_dod_judgement", "rubric_digest"),
        (f"{_C}._dispatcher_dod_judgement_candidates", "run_candidate_chain"),
        (f"{_C}._dispatcher_dod_judgement_markers", "is_receipt_comment"),
        (f"{_C}._dispatcher_dod_judgement_record", "did_not_run_comment"),
        (f"{_C}._dispatcher_dod_judgement_record", "verdict_comment"),
        (f"{_C}._dispatcher_dod_judgement_run", "judgement_prompt"),
        (f"{_C}._dispatcher_dod_judgement_run", "judgement_rubric"),
        (f"{_C}._dispatcher_dod_spec_identity", "SpecIdentity"),
        (f"{_C}._dispatcher_dod_spec_identity", "spec_identity_for_governing"),
        (f"{_C}._dispatcher_io", "ShellCommandRunner"),
        (f"{_C}._dispatcher_paths", "store_config"),
        (f"{_C}._dod_governing_heading", "governing_heading_findings"),
        (f"{_C}._dod_governing_heading_judge", "host_governing_heading_reader"),
    }
)


def _registered_install_scripts() -> list[Path]:
    """Every `dev-tooling/` script that resolves the package from the install registry."""
    return sorted(
        path
        for path in _DEV_TOOLING.iterdir()
        if path.is_file()
        and path.suffix == ".sh"
        and _REGISTRY_MARKER in path.read_text(encoding="utf-8")
    )


def _catches_import_error(*, handler: ast.ExceptHandler) -> bool:
    caught = handler.type
    names = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return any(isinstance(name, ast.Name) and name.id in _IMPORT_ERRORS for name in names)


def _unguarded_package_imports(*, source: str) -> set[tuple[str, str]]:
    """(module, name) of each package import outside an ImportError-guarded try body.

    An import inside the HANDLER is unguarded: it runs exactly when the guarded
    import failed, so it must resolve on the predating build.
    """
    tree = ast.parse(source)
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
            _catches_import_error(handler=handler) for handler in node.handlers
        ):
            guarded.update(id(inner) for statement in node.body for inner in ast.walk(statement))
    return {
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith(_PACKAGE)
        and id(node) not in guarded
        for alias in node.names
    }


def _script_imports(*, script: Path) -> set[tuple[str, str]]:
    text = script.read_text(encoding="utf-8")
    return {
        entry
        for heredoc in _HEREDOC.finditer(text)
        for entry in _unguarded_package_imports(source=heredoc["body"])
    }


def _top_level_names(*, module: str) -> set[str] | None:
    relative = Path(*module.split("."))
    for candidate in (relative.with_suffix(".py"), relative / "__init__.py"):
        path = _PACKAGE_SCRIPTS / candidate
        if path.is_file():
            names: set[str] = set()
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                    names.add(node.name)
                elif isinstance(node, ast.Assign):
                    names.update(t.id for t in node.targets if isinstance(t, ast.Name))
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    names.add(node.target.id)
                elif isinstance(node, ast.Import | ast.ImportFrom):
                    names.update((a.asname or a.name).split(".")[0] for a in node.names)
            return names
    return None


def test_the_scan_finds_the_repository_preflight() -> None:
    """The control is not vacuous: it reaches the one script the incident broke."""
    scripts = _registered_install_scripts()

    assert _DEV_TOOLING / "dod-preflight.sh" in scripts
    assert _script_imports(script=_DEV_TOOLING / "dod-preflight.sh")


def test_every_unguarded_import_is_shipped_by_the_registered_build() -> None:
    """An import the registered build may lack must carry an ImportError fallback."""
    beyond_floor = {
        script.name: sorted(_script_imports(script=script) - _REGISTERED_BUILD_FLOOR)
        for script in _registered_install_scripts()
    }

    assert {name: entries for name, entries in beyond_floor.items() if entries} == {}


def test_the_floor_names_only_what_this_tree_still_ships() -> None:
    """A floor entry this tree no longer defines would break the next release's script."""
    absent = sorted(
        (module, name)
        for module, name in _REGISTERED_BUILD_FLOOR
        if name not in (_top_level_names(module=module) or set())
    )

    assert absent == []
