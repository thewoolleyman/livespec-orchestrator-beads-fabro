"""Coverage for the committed `dispatcher.idle_slot_audit` object's three outcomes.

The malformed cases are parametrized against the KEY each one must name,
because a refusal that reports the wrong key is the failure this reader exists
to prevent: an operator told `priority` is wrong while `factory` is the broken
half edits the healthy value.
"""

import importlib
import json
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_idle_slot_config.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_config"
_FACTORIES = {"hp": {"server": "https://hp.example:32276"}}


def _write(root: Path, *, dispatcher: dict[str, object]) -> None:
    (root / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}, indent=2),
        encoding="utf-8",
    )


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def _resolve(root: Path) -> object:
    return _module().resolve_idle_slot_audit(cwd=root)


def test_a_wellformed_object_parses_to_the_factory_and_the_priority_sets(
    tmp_path: Path,
) -> None:
    """Both subject forms, and configuration order preserved across them."""
    assert _MODULE_PATH.is_file()
    _write(
        tmp_path,
        dispatcher={
            "factories": _FACTORIES,
            "idle_slot_audit": {
                "factory": "hp",
                "priority": [
                    {"repo": "../dev-tooling", "epic": "dt-epic"},
                    {"repo": "/abs/other", "items": ["o-1", "o-2"]},
                ],
            },
        },
    )

    config = _resolve(tmp_path)

    assert config.factory == "hp"
    assert [(entry.repo, entry.epic, entry.items) for entry in config.priority] == [
        ("../dev-tooling", "dt-epic", ()),
        ("/abs/other", None, ("o-1", "o-2")),
    ]


def test_an_absent_object_is_not_configured_rather_than_a_fault(tmp_path: Path) -> None:
    """A repository that declares no priority set has nothing to audit."""
    assert _MODULE_PATH.is_file()
    _write(tmp_path, dispatcher={"factories": _FACTORIES})

    assert _resolve(tmp_path) is None


@pytest.mark.parametrize(
    ("audit", "key"),
    [
        ("not-an-object", "dispatcher.idle_slot_audit is not an object"),
        ({"priority": [{"repo": "r", "epic": "e"}]}, "dispatcher.idle_slot_audit.factory"),
        (
            {"factory": "", "priority": [{"repo": "r", "epic": "e"}]},
            "dispatcher.idle_slot_audit.factory",
        ),
        (
            {"factory": "undeclared", "priority": [{"repo": "r", "epic": "e"}]},
            "dispatcher.idle_slot_audit.factory",
        ),
        ({"factory": "hp"}, "dispatcher.idle_slot_audit.priority"),
        ({"factory": "hp", "priority": []}, "dispatcher.idle_slot_audit.priority"),
        ({"factory": "hp", "priority": ["r"]}, "dispatcher.idle_slot_audit.priority[0]"),
        (
            {"factory": "hp", "priority": [{"epic": "e"}]},
            "dispatcher.idle_slot_audit.priority[0].repo",
        ),
        (
            {"factory": "hp", "priority": [{"repo": "r", "epic": "e", "items": ["i"]}]},
            "dispatcher.idle_slot_audit.priority[0] carries both epic and items",
        ),
        (
            {"factory": "hp", "priority": [{"repo": "r", "epic": 7}]},
            "dispatcher.idle_slot_audit.priority[0].epic",
        ),
        (
            {"factory": "hp", "priority": [{"repo": "r"}]},
            "dispatcher.idle_slot_audit.priority[0].items",
        ),
        (
            {"factory": "hp", "priority": [{"repo": "r", "items": []}]},
            "dispatcher.idle_slot_audit.priority[0].items",
        ),
        (
            {"factory": "hp", "priority": [{"repo": "r", "items": [""]}]},
            "dispatcher.idle_slot_audit.priority[0].items",
        ),
        (
            {"factory": "hp", "priority": [{"repo": "r", "epic": "e"}, {"repo": 1, "epic": "e"}]},
            "dispatcher.idle_slot_audit.priority[1].repo",
        ),
    ],
)
def test_a_malformed_object_refuses_naming_the_offending_key(
    tmp_path: Path, audit: object, key: str
) -> None:
    """Each refusal names the key that is wrong, never a healthy neighbour."""
    assert _MODULE_PATH.is_file()
    _write(tmp_path, dispatcher={"factories": _FACTORIES, "idle_slot_audit": audit})

    finding = _resolve(tmp_path)

    assert isinstance(finding, str)
    assert key in finding


def test_an_entry_repo_resolves_relative_to_this_repositorys_root(tmp_path: Path) -> None:
    """A relative path is joined to the root; an absolute one is taken as given."""
    assert _MODULE_PATH.is_file()
    module = _module()
    relative = module.PriorityEntry(repo="../sibling", epic="e", items=())
    absolute = module.PriorityEntry(repo="/elsewhere/sibling", epic="e", items=())

    assert module.priority_entry_root(project_root=tmp_path, entry=relative) == (
        tmp_path / "../sibling"
    )
    assert module.priority_entry_root(project_root=tmp_path, entry=absolute) == Path(
        "/elsewhere/sibling"
    )
