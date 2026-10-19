"""Coverage for the `idle-slot-audit` subcommand's rendering and exit status.

An unreadable tenant is asserted here rather than left implicit: the listing
must NAME it, because an entry silently dropped from the output reads as a
tenant with nothing to dispatch.
"""

import argparse
import importlib
import json
from pathlib import Path

import pytest

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE_PATH = _COMMANDS / "_dispatcher_idle_slot_command.py"
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_command"
_AUDIT_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_audit"
_BOARD_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_board"
_CLASSIFY_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_classify"


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def _child(
    *,
    id_: str,
    classification: str,
    status: str = "ready",
    reason: str | None = None,
    blockers: tuple[tuple[str, str], ...] = (),
) -> object:
    classify = importlib.import_module(_CLASSIFY_NAME)
    return classify.ClassifiedChild(
        id=id_,
        status=status,
        classification=classification,
        reason=reason,
        blockers=tuple(
            classify.BlockerView(id=blocker_id, status=blocker_status)
            for blocker_id, blocker_status in blockers
        ),
    )


def _result(
    *,
    board: object,
    entries: tuple[object, ...] = (),
    configured: bool = True,
    configuration_finding: str | None = None,
) -> object:
    return importlib.import_module(_AUDIT_NAME).IdleSlotAuditResult(
        configured=configured,
        configuration_finding=configuration_finding,
        factory="hp" if configured else None,
        board=board,
        entries=entries,
    )


def _entry(
    *,
    repo: str,
    epic: str | None = None,
    item_ids: tuple[str, ...] = (),
    unreadable: bool = False,
    children: tuple[object, ...] = (),
    missing_ids: tuple[str, ...] = (),
) -> object:
    return importlib.import_module(_AUDIT_NAME).EntryAudit(
        repo=repo,
        root=f"/repos/{repo}",
        epic=epic,
        item_ids=item_ids,
        unreadable=unreadable,
        children=children,
        missing_ids=missing_ids,
    )


def _observable(*, live: int = 1, queued: int = 0) -> object:
    return importlib.import_module(_BOARD_NAME).BoardReading(
        observable=True, live_count=live, queued_count=queued, live_item_ids=frozenset()
    )


def test_the_rendering_shows_each_child_its_blockers_and_the_missing_ids() -> None:
    """One line per child, carrying its class, status, blockers and reason."""
    assert _MODULE_PATH.is_file()
    module = _module()
    result = _result(
        board=_observable(),
        entries=(
            _entry(
                repo="tenant-a",
                epic="a-epic",
                children=(
                    _child(
                        id_="a-1",
                        classification="BLOCKED",
                        blockers=(("a-blocker", "active"),),
                    ),
                    _child(id_="a-2", classification="HELD", reason="refused at the wall"),
                ),
            ),
            _entry(repo="tenant-b", item_ids=("b-1",), missing_ids=("b-1",)),
        ),
    )

    text = module.render_idle_slot_audit(result=result)

    assert "idle-slot audit — factory hp" in text
    assert "board: live 1, queued 0" in text
    assert "tenant-a  epic a-epic" in text
    assert "a-1  BLOCKED  status=ready  open-blocks=a-blocker(active)" in text
    assert "a-2  HELD  status=ready  reason=refused at the wall" in text
    assert "tenant-b  items b-1" in text
    assert "MISSING  b-1  absent from its tenant" in text


def test_an_unreadable_tenant_renders_as_unreadable_with_its_root() -> None:
    """The entry is still printed: a dropped tenant reads as a tenant with no work."""
    assert _MODULE_PATH.is_file()
    module = _module()

    text = module.render_idle_slot_audit(
        result=_result(
            board=_observable(),
            entries=(_entry(repo="tenant-a", epic="a-epic", unreadable=True),),
        )
    )

    assert "tenant-a  epic a-epic  UNREADABLE-TENANT at /repos/tenant-a" in text


def test_an_unconfigured_repository_says_so_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing to audit is not a refusal, so the status stays zero."""
    assert _MODULE_PATH.is_file()
    module = _module()
    (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")

    exit_code = module.run_idle_slot_audit_command(
        args=argparse.Namespace(repo=str(tmp_path), as_json=False)
    )

    assert exit_code == 0
    assert module.NOT_CONFIGURED_LINE in capsys.readouterr().out


def test_a_malformed_configuration_refuses_with_a_nonzero_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The clause makes a malformed object a refusal, not an empty result."""
    assert _MODULE_PATH.is_file()
    module = _module()
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"idle_slot_audit": {"factory": "nope"}}
                }
            }
        ),
        encoding="utf-8",
    )

    exit_code = module.run_idle_slot_audit_command(
        args=argparse.Namespace(repo=str(tmp_path), as_json=True)
    )

    assert exit_code == module.CONFIGURATION_REFUSAL_EXIT
    payload = json.loads(capsys.readouterr().out)
    assert "dispatcher.idle_slot_audit.factory" in payload["configuration_finding"]

    text_exit = module.run_idle_slot_audit_command(
        args=argparse.Namespace(repo=str(tmp_path), as_json=False)
    )

    assert text_exit == module.CONFIGURATION_REFUSAL_EXIT
    assert "idle-slot audit refused: configuration finding:" in capsys.readouterr().out


def test_the_subcommand_defaults_its_repo_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--repo` is optional, and omitting it audits the current checkout."""
    assert _MODULE_PATH.is_file()
    module = _module()
    (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = module.run_idle_slot_audit_command(
        args=argparse.Namespace(repo=None, as_json=False)
    )

    assert exit_code == 0
    assert module.NOT_CONFIGURED_LINE in capsys.readouterr().out


def test_the_handoff_command_is_the_read_only_audit_invocation(tmp_path: Path) -> None:
    """The inspection handoff names this subcommand and this repository."""
    assert _MODULE_PATH.is_file()
    module = _module()

    command = module.idle_slot_audit_command(project_root=tmp_path)

    assert "dispatcher.py" in command
    assert "idle-slot-audit" in command
    assert str(tmp_path) in command
    assert "--json" in command


def test_the_arguments_are_the_read_only_repo_and_json_pair() -> None:
    """A read-only subcommand takes no mutating flag, so none is declared."""
    assert _MODULE_PATH.is_file()
    module = _module()
    parser = argparse.ArgumentParser(prog="idle-slot-audit")

    module.add_idle_slot_audit_arguments(parser=parser)

    parsed = parser.parse_args(["--repo", "/repo", "--json"])
    assert (parsed.repo, parsed.as_json) == ("/repo", True)
