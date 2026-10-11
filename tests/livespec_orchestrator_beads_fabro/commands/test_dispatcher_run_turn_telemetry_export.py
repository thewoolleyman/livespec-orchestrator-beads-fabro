"""Whether a dispatch's factory exports `run_turn` telemetry this host can read.

The guard this feeds reported observability from the literal factory name `hp`
until this module existed, so every OTHER factory — a Petri-era candidate
instance beside the pinned one, a second host, a locally served engine — was
reported observable by default and the one genuinely unobservable factory was
recognised only by its spelling.

WHAT IS ASSERTED, AND WHY EACH HALF NEEDS THE OTHER. A resolver that answered
"unobservable" for everything would satisfy the `hp`-shaped case perfectly well,
so the declared-`dispatcher_receiver` case is its control; and a resolver that
answered "observable" for everything would satisfy that one just as well, so the
server-bearing undeclared case is the control for it. The two undeclared arms are
the ones a name test cannot express at all, and they are what keep this change
from moving any factory this repository actually dispatches to: a factory naming
a server reads exactly as `hp` did, and a factory naming none reads exactly as
the implicit single-factory target did.

AN UNRECOGNISED DECLARATION IS ASSERTED TO READ AS UNOBSERVABLE RATHER THAN TO
REFUSE. The guard is a non-blocking post-verdict assertion, so a refusal would
fail an already-merged dispatch over a telemetry gauge, and the opposite
fallback would let a value this build cannot interpret stand as proof that the
receiver saw the factory's spans. `_dispatcher_secret_channel` refuses its own
unrecognised declaration for the mirror-image reason, and that asymmetry is
deliberate: there the wrong guess persists a credential.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_telemetry_export"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_run_turn_telemetry_export.py"
)

# The remote factory this repository dispatches to, and the shape its entry has
# today: a server and no telemetry-export declaration.
_REMOTE_ENTRY: dict[str, object] = {"server": "https://hp-xubuntu.perch-rudd.ts.net:32276"}


def _export() -> Any:
    """Import the resolver, asserting the file exists first.

    The `is_file()` assertion is what makes this a genuine failing assertion
    before the module is written, rather than a collection-time import error that
    proves only unimportability.
    """
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


def _block(*, entry: dict[str, object], factory: str = "hp") -> dict[str, Any]:
    return {"factories": {factory: entry}}


def test_run_turn_telemetry_export_names_its_key_and_both_self_describing_values() -> None:
    export = _export()

    assert export.RUN_TURN_TELEMETRY_EXPORT_KEY == "run_turn_telemetry_export"
    assert export.RUN_TURN_TELEMETRY_EXPORTS == ("dispatcher_receiver", "none")


def test_factory_declaring_the_dispatcher_receiver_is_observable() -> None:
    export = _export()
    entry = dict(_REMOTE_ENTRY)
    entry[export.RUN_TURN_TELEMETRY_EXPORT_KEY] = (
        export.RUN_TURN_TELEMETRY_EXPORT_DISPATCHER_RECEIVER
    )

    assert export.factory_run_turn_observable(block=_block(entry=entry), factory="hp") is True


@pytest.mark.parametrize(
    "declared",
    ["none", "", "honeycomb", 7, None],
    ids=["none", "empty", "unrecognised", "non-string", "null"],
)
def test_factory_declaring_anything_but_the_receiver_is_unobservable(declared: object) -> None:
    export = _export()
    entry = dict(_REMOTE_ENTRY)
    entry[export.RUN_TURN_TELEMETRY_EXPORT_KEY] = declared

    assert export.factory_run_turn_observable(block=_block(entry=entry), factory="hp") is False


def test_undeclared_factory_naming_a_server_is_unobservable_as_hp_reads_today() -> None:
    export = _export()

    assert (
        export.factory_run_turn_observable(block=_block(entry=dict(_REMOTE_ENTRY)), factory="hp")
        is False
    )


@pytest.mark.parametrize(
    "entry",
    [
        None,
        {},
        {"server": ""},
        {"server": "   "},
        {"server": 7},
        "not-a-mapping",
    ],
    ids=[
        "no-factories-block",
        "entry-names-nothing",
        "empty-server",
        "whitespace-server",
        "non-string-server",
        "entry-is-not-a-mapping",
    ],
)
def test_undeclared_factory_naming_no_server_is_observable_as_the_local_target_reads(
    entry: object,
) -> None:
    export = _export()
    block: dict[str, Any] = {} if entry is None else {"factories": {"hp": entry}}

    assert export.factory_run_turn_observable(block=block, factory="hp") is True


def test_factory_absent_from_a_declared_factories_block_is_observable() -> None:
    export = _export()

    assert (
        export.factory_run_turn_observable(
            block=_block(entry=dict(_REMOTE_ENTRY), factory="other"), factory="hp"
        )
        is True
    )


def test_unreadable_configuration_is_unobservable_rather_than_observable() -> None:
    export = _export()

    assert export.factory_run_turn_observable(block=None, factory="hp") is False


def test_run_turn_telemetry_block_reads_the_dispatch_targets_factories(tmp_path: Path) -> None:
    export = _export()
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"factories": '
        '{"hp": {"server": "https://hp.example", "run_turn_telemetry_export": "none"}}}}}',
        encoding="utf-8",
    )

    block = export.run_turn_telemetry_block(repo=tmp_path)

    assert export.factory_run_turn_observable(block=block, factory="hp") is False


def test_run_turn_telemetry_block_reads_an_unparseable_configuration_as_absent(
    tmp_path: Path,
) -> None:
    export = _export()
    _ = (tmp_path / ".livespec.jsonc").write_text("{ not json", encoding="utf-8")

    assert export.run_turn_telemetry_block(repo=tmp_path) is None
