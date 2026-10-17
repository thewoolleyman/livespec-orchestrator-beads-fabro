"""The committed canary fixture — what it defines, and what refuses it.

The fixture is the whole point of `bd-ib-tixpma`: canaries 5 and 6 of plan
`fabro-currency` were taken against a real backlog item whose reference line
named a heading governing something else, so both were refused at `dod_gate` and
measured the ITEM rather than the engine. These tests pin the committed fixture
against the ONE ratified Definition-of-Done parse the gate's host-side wall also
reads, so a fixture that would be refused there cannot sit in the repository
looking fileable.

The module is reached through `import_module` rather than a top-level import so
the first assertion of each test is a genuine one about the artifact rather than
a collection error about the module.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import (
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig
from returns.io import IOFailure

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_canary"
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_canary.py"
)


def _canary() -> Any:
    return import_module(_MODULE_NAME)


def _fake_config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-orch-beads-fabro",
        prefix="bd-ib",
        server_user="livespec-orch-beads-fabro",
        database="livespec-orch-beads-fabro",
        bd_path="bd",
        fake=True,
        repo_root=_REPO_ROOT,
    )


def _repo_whose_fixture_references(*, tmp_path: Path, heading: str) -> Path:
    """A repository holding the committed fixture with ONE line changed.

    Only the `References:` line differs, so the copy is still a well-formed
    fixture that the parse admits and the wall then grades — which is what makes
    the routing the thing under test rather than the parse.
    """
    canary = _canary()
    committed = (_REPO_ROOT / canary.CANARY_FIXTURE_RELATIVE_PATH).read_text(encoding="utf-8")
    before, marker, _ = committed.partition("References:")
    assert marker, canary.CANARY_FIXTURE_RELATIVE_PATH
    doctored = tmp_path / canary.CANARY_FIXTURE_RELATIVE_PATH
    doctored.parent.mkdir(parents=True, exist_ok=True)
    doctored.write_text(f"{before}References: {heading}\n", encoding="utf-8")
    return tmp_path


def test_the_committed_fixture_template_defines_the_canary_work_item() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    fixture_path = _REPO_ROOT / canary.CANARY_FIXTURE_RELATIVE_PATH
    assert fixture_path.is_file(), canary.CANARY_FIXTURE_RELATIVE_PATH

    parsed = canary.read_canary_fixture(repo=_REPO_ROOT)
    assert isinstance(parsed, canary.CanaryFixture), parsed

    # A title, and a description that is NOT the title: the title must not be
    # the description's own first heading, because that is what the ratified
    # parse keys the Definition of Done on.
    assert parsed.title.strip()
    assert parsed.title not in parsed.description

    section = definition_of_done(description=parsed.description)
    assert section.present
    assert section.assertions
    assert section.references
    assert section.malformed_proof_modes == ()

    # The fixture's one deliverable is the dedicated marker file, so its
    # assertion has to name that file rather than any product surface.
    assert canary.CANARY_MARKER_RELATIVE_PATH in section.assertions[0].text


def test_a_fixture_without_a_title_line_is_refused() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.parse_canary_fixture(text="no heading at all\n")

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "no `# ` title line" in refused.detail


def test_a_fixture_whose_title_line_is_empty_is_refused() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.parse_canary_fixture(text="#  \n\n## Definition of Done\n")

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "title line carries no text" in refused.detail


def test_a_fixture_whose_description_carries_no_section_is_refused() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.parse_canary_fixture(text="# Canary\n\nprose only\n")

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "no Definition of Done section" in refused.detail


def test_a_fixture_whose_section_carries_no_assertion_is_refused() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.parse_canary_fixture(
        text="# Canary\n\n## Definition of Done\n\nReferences: ## Fabro runtime constraints\n"
    )

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "no gradeable assertion" in refused.detail


def test_a_fixture_whose_section_carries_no_reference_line_is_refused() -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.parse_canary_fixture(
        text="# Canary\n\n## Definition of Done\n\n- The marker file carries one line.\n"
    )

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "no `References:` line" in refused.detail


def test_an_unreadable_fixture_names_the_path_rather_than_raising(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    canary = _canary()

    refused = canary.read_canary_fixture(repo=tmp_path)

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert canary.CANARY_FIXTURE_RELATIVE_PATH in refused.detail
    assert str(tmp_path) in refused.detail


def test_an_intake_route_that_fails_names_the_minted_id(*, monkeypatch: Any) -> None:
    """A filed-but-unrouted canary must not vanish.

    The record EXISTS in the ledger by the time intake refuses, so the refusal
    carries the minted id — otherwise the canary is an orphan nobody can find to
    dispose of. The intake seam is substituted rather than provoked through a
    doctored repository: a malformed configuration refuses EARLIER, at store
    resolution, so it would exercise a different arm than the one under test.
    """
    canary = _canary()
    monkeypatch.setattr(
        canary,
        "file_captured_work_item",
        lambda **_: IOFailure(WorkItemNotFoundError(item_id="bd-ib-absent")),
    )

    refused = canary.file_canary_work_item(
        repo=_REPO_ROOT, config=_fake_config(), now_iso="2026-10-16T00:00:00Z"
    )

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "intake could not route it" in refused.detail
    assert "bd-ib-" in refused.detail


def test_an_intake_route_that_parks_the_canary_is_refused(tmp_path: Path) -> None:
    """A canary intake did not route to `ready` must not reach the dispatch.

    This is the fault that refused canaries 5 and 6 — a `References:` line
    naming a heading the governed tree does not carry — reproduced through the
    REAL host-side wall rather than a substituted seam, because the seam cannot
    show that the wall is what withholds `ready`. Intake succeeds, so the
    `IOResult` is a success and the id is minted; only the routed VERDICT says
    the item is parked. A filing graded on success alone therefore prints that
    id, the recipe's emptiness guard passes, and the canary is dispatched at
    `pending-approval` — an item-quality failure arriving at the factory wearing
    an engine failure's clothes, which is the one outcome the committed fixture
    exists to remove.

    The routed status is asserted IN the detail: "intake refused it" and "intake
    parked it awaiting approval" are different faults with different remedies,
    and an operator who cannot tell them apart reads the second as the first.
    """
    canary = _canary()
    reset_fake_singleton()
    config = _fake_config()
    repo = _repo_whose_fixture_references(
        tmp_path=tmp_path,
        heading="## Scenario 999 — no heading of the governed spec tree carries this",
    )

    refused = canary.file_canary_work_item(repo=repo, config=config, now_iso="2026-10-16T00:00:00Z")

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
    assert "pending-approval" in refused.detail
    assert "ready" in refused.detail
    # The minted id, for the same reason the unroutable arm names it: the record
    # EXISTS in the ledger by now, and a refusal that hid the id would leave an
    # orphan nobody could find to dispose of.
    parked = materialize_work_items(records=read_work_items(path=config))
    assert len(parked) == 1, parked
    [item_id] = parked
    assert item_id in refused.detail
    assert parked[item_id].status == "pending-approval"


def test_the_subcommand_refuses_when_intake_cannot_route(*, capsys: Any, monkeypatch: Any) -> None:
    canary = _canary()
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setattr(
        canary,
        "file_captured_work_item",
        lambda **_: IOFailure(WorkItemNotFoundError(item_id="bd-ib-absent")),
    )

    class _Args:
        repo = str(_REPO_ROOT)

    exit_code = canary.run_file_canary_command(args=_Args())

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "LIVESPEC_CANARY_FIXTURE_UNUSABLE" in captured.err
    assert "intake could not route it" in captured.err


def test_every_filed_canary_carries_the_fixture_dispatch_label() -> None:
    """The label is what tells a fixture dispatch from ordinary filed work.

    It is asserted on the LEDGER RECORD rather than on a constant, because the
    canary's whole point is that a reader surveying the tenant can separate the
    canaries out; a label the code names and never writes would read correct at
    every other surface.
    """
    canary = _canary()
    assert hasattr(canary, "CANARY_LABEL"), dir(canary)
    reset_fake_singleton()
    config = _fake_config()

    filed = canary.file_canary_work_item(
        repo=_REPO_ROOT, config=config, now_iso="2026-10-16T00:00:00Z"
    )

    assert isinstance(filed, str), filed
    record = make_beads_client(config=config).show_issue(issue_id=filed)
    assert canary.CANARY_LABEL in (record.get("labels") or [])
    # Prefixed and self-describing, so a bare label list identifies it without a
    # legend, and never a numbered or tiered name.
    assert canary.CANARY_LABEL.startswith("canary:")
    # Beside the intake marker rather than instead of it: the canary is a real
    # ledger item that went through the ordinary door.
    assert "intake:triaged" in (record.get("labels") or [])
