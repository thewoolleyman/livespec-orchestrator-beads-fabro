"""Scenario 182 — a registry-backed factory's address comes from the host registry.

Binds `SPECIFICATION/scenarios.md` Scenario 182 and the host-factory-registry
clause of `SPECIFICATION/contracts.md`. Every case starts from a
`.livespec.jsonc` and a registry JSON file ON DISK and runs the production
configuration, resolution, pre-claim grading and plan seams; the only things
stood in are the `fabro` CLI (a recording runner, so the launch argv is
observable without a server) and the ledger, through this repository's own
hermetic `FakeBeadsClient`.

WHY THE ADDRESS IS ASSERTED AT THE ARGV AND AT THE LEDGER, not at the resolver.
`resolve_fabro_factory` answering with the registry's address proves the reading;
it does not prove the address REACHES the run. The address crosses four hand-offs
after resolution — the dispatch target, the plan, the port's argv, and the
ledger's dispatch-factory record — and a registry-backed entry is exactly the
case where a hand-off can drop it silently, because the committed entry carries
no `server` for anything downstream to fall back to. A dropped address does not
fail: it resolves to None, which every surface reads as "this factory declares no
server" and therefore as the AMBIENT LOCAL factory. So the run would be created,
on the wrong machine, with nothing in the record saying so.

WHY THE REFUSAL IS TAKEN OFF `dispatch_preamble` AND THE LEDGER IS READ BACK.
"Refused before any claim, ledger write of any kind, or Fabro run creation" is
two claims, and a refusal string proves only the first. The preamble is the whole
of what runs ahead of admission, so the item is snapshotted before it and
compared after: an unresolvable registry that refuses AFTER stamping would
satisfy a message-only assertion while leaving the row `active` under a dispatch
that never placed work.

WHY THE `env unset` PATH CASE ASSERTS A NEGATIVE AS WELL AS THE CONSTANT.
Asserting only that `registry_path()` returns `/etc/livespec/fabro-factories.json`
is an echo of the constant. The discriminating assertion is that with the
variable unset the resolution does NOT return the override file's address — which
an implementation reading the override unconditionally could not satisfy — and it
is hermetic either way, because a host that happens to carry the default file
cannot map `petri` to this test's own address.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_factory
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_environment import (
    factory_declaration_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger import (
    resolve_dispatch_factory_target,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import stamp_dispatch_run
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_port import (
    SandboxContainerPort,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import fabro_port_for_plan
from livespec_orchestrator_beads_fabro.commands.dispatcher import dispatch_preamble
from livespec_orchestrator_beads_fabro.store import record_dispatch_factory
from livespec_orchestrator_beads_fabro.types import StoreConfig

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_READING_MODULE = "livespec_orchestrator_beads_fabro.commands._factory_registry"
_GRADE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_factory_registry"

_FACTORY = "petri"
# A RESERVED-domain sentinel, not the address this factory really resolves to, and
# it must stay one: the default-registry-path case below asserts that resolution
# does NOT return this value, and reads the real host
# `/etc/livespec/fabro-factories.json` to do it. Spelled as a machine this fleet
# provisions, that assertion is false on exactly the host the registry maps
# `petri` on — a false FAIL on every `just check` there, while the code is
# correct. `.example` is reserved by RFC 2606, so no inventory can render it.
_REGISTRY_SERVER = "https://registry-override.example:32276"
_REGISTRY_DOCKER_HOST = "ssh://cwoolley@gmktec.perch-rudd.ts.net"
_OTHER_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_SPEC_DEFAULT_REGISTRY_PATH = "/etc/livespec/fabro-factories.json"
_REGISTRY_PATH_ENV_VAR = "LIVESPEC_FABRO_FACTORY_REGISTRY"
_FACTORY_SELECTION_ENV_VAR = "LIVESPEC_FABRO_FACTORY"

_TENANT = "livespec-orch-beads-fabro"
_PREFIX = "bd-ib"
_WORK_ITEM_ID = "bd-ib-fubkcv"
_RUN_ID = "01M580PF02S0VMFKX5HPB05Z8C"
_EXIT_PRECONDITION_ERROR = 3


@pytest.fixture(autouse=True)
def _hermetic_registry_env(monkeypatch: pytest.MonkeyPatch) -> object:
    """A fresh in-memory tenant, and neither routing variable inherited.

    Both deletions are load-bearing rather than hygiene. `LIVESPEC_FABRO_FACTORY`
    is the scenario's own Background and overrides every selection below, so a
    value leaking in from the dispatch that runs this suite would decide these
    cases instead of the configuration they declare. The registry path variable
    is the subject of one case and the override of all the others.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:factory-registry-scenario182")
    monkeypatch.delenv(_FACTORY_SELECTION_ENV_VAR, raising=False)
    monkeypatch.delenv(_REGISTRY_PATH_ENV_VAR, raising=False)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Runner:
    """Records every argv a port hands a CLI — the `fabro` launch and `docker`."""

    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.argvs.append(argv)
        return CommandResult(exit_code=0, stdout=f"Run: {_RUN_ID}\n", stderr="")


def _reading_module() -> Any:
    """The registry READING module, imported inside the test body.

    The module path is asserted FIRST so the Red is a genuine assertion failure
    rather than a collection error: at Red the module does not exist, and a
    top-level import of it would die before any assertion ran.
    """
    assert (_COMMANDS_DIR / "_factory_registry.py").is_file()
    return importlib.import_module(_READING_MODULE)


def _grade_module() -> Any:
    """The registry GRADE module, imported inside the test body."""
    assert (_COMMANDS_DIR / "_dispatcher_factory_registry.py").is_file()
    return importlib.import_module(_GRADE_MODULE)


def _store() -> StoreConfig:
    """The hermetic tenant every case reads and writes through."""
    return StoreConfig(
        tenant=_TENANT,
        prefix=_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_store())
    assert isinstance(client, FakeBeadsClient)
    return client


def _seed_item() -> None:
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=_WORK_ITEM_ID,
            issue_type="feature",
            title="Resolve a registry-backed factory's address",
            description="## Definition of Done\n\n- The address comes from the registry.\n",
            assignee=None,
            created_at="2026-10-18T00:00:00Z",
        )
    )


def _item_state() -> dict[str, Any]:
    """The item's status, metadata and comments, as one comparable snapshot."""
    record = _fake().show_issue(issue_id=_WORK_ITEM_ID)
    return {
        "status": record.get("status"),
        "assignee": record.get("assignee"),
        "metadata": json.dumps(record.get("metadata"), sort_keys=True, default=repr),
        "comments": [comment.text for comment in _fake().list_comments(issue_id=_WORK_ITEM_ID)],
    }


def _write_config(
    *,
    cwd: Path,
    factories: dict[str, Any],
    default_factory: str | None = None,
) -> None:
    dispatcher: dict[str, Any] = {"factories": factories}
    if default_factory is not None:
        dispatcher["default_factory"] = default_factory
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"tenant": _TENANT, "prefix": _PREFIX, "fake": True},
                    "dispatcher": dispatcher,
                }
            }
        ),
        encoding="utf-8",
    )


def _write_registry(*, path: Path, payload: object) -> None:
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def _point_at_registry(*, monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv(_REGISTRY_PATH_ENV_VAR, str(path))


def _registry_backed_repo(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: object,
    committed: dict[str, Any] | None = None,
) -> None:
    """A repo declaring `petri` as registry-backed, beside a registry naming it."""
    declared: dict[str, Any] = {"registry": True}
    declared.update(committed or {})
    _write_config(cwd=cwd, factories={_FACTORY: declared}, default_factory=_FACTORY)
    registry = cwd / "fabro-factories.json"
    _write_registry(path=registry, payload={_FACTORY: entry})
    _point_at_registry(monkeypatch=monkeypatch, path=registry)


def _run_argv(*, cwd: Path, runner: _Runner, server: str | None) -> list[str]:
    """The `fabro run` argv one dispatch to `server` actually produces."""
    plan = build_plan(
        repo=cwd,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=cwd / "workflow.toml",
        goal_file=cwd / "goal.md",
        fabro_bin="/opt/fabro",
        fabro_factory_name=_FACTORY,
        fabro_factory_server=server,
        janitor=None,
        janitor_checkout=cwd / "janitor",
    )
    port = fabro_port_for_plan(plan=plan, runner=runner)
    _ = port.run(
        workflow_toml=plan.workflow_toml,
        goal_file=plan.goal_file,
        inputs=(),
        timeout_seconds=42.0,
    )
    return next(argv for argv in runner.argvs if argv[1] == "run")


def test_a_registry_backed_dispatch_runs_on_the_registry_address_and_records_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The registry's address reaches the run argv and the item's own record.

    Three assertions in one case because they are three points on ONE hand-off
    chain and a failure has to say which point dropped the address: the resolver,
    the launch argv, or the ledger stamp. Splitting them would re-run the chain
    three times to learn the same thing, and a per-point case could not tell an
    address the resolver never produced from one the chain lost.

    `--server` is asserted as the LAST two argv tokens because the pinned engine
    requires it to stay last on the subcommand, and as adjacent TOKENS rather
    than by substring because an address spliced onto the flag would satisfy a
    substring probe and be rejected by the engine.
    """
    _registry_backed_repo(cwd=tmp_path, monkeypatch=monkeypatch, entry={"server": _REGISTRY_SERVER})
    _seed_item()
    _ = _reading_module()

    target = resolve_fabro_factory(cwd=tmp_path, factory=_FACTORY)

    assert target.name == _FACTORY
    assert target.server == _REGISTRY_SERVER

    argv = _run_argv(cwd=tmp_path, runner=_Runner(), server=target.server)

    assert argv[-2:] == ["--server", _REGISTRY_SERVER]

    plan = build_plan(
        repo=tmp_path,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="/opt/fabro",
        fabro_factory_name=target.name,
        fabro_factory_server=target.server,
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )
    _ = stamp_dispatch_run(
        plan=plan,
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        run_id=_RUN_ID,
    )

    metadata = _fake().show_issue(issue_id=_WORK_ITEM_ID).get("metadata")
    assert isinstance(metadata, dict)
    assert metadata["dispatch_factory"] == {"name": _FACTORY, "server": _REGISTRY_SERVER}


def test_a_resume_resolves_the_registry_address_the_recorded_pin_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A resume addresses the registry's address, through the item's own pin.

    A resume carries no `--factory`: it resolves through
    `resolve_dispatch_factory_target`, which takes the item's RECORDED pin. That
    is a different selection leg from the dispatch case above — the name arrives
    from the ledger rather than from the command line — and it is the leg a
    registry-backed entry can regress on alone, because the pin is a bare name
    with no address beside it.
    """
    _registry_backed_repo(cwd=tmp_path, monkeypatch=monkeypatch, entry={"server": _REGISTRY_SERVER})
    _seed_item()
    record_dispatch_factory(path=_store(), work_item_id=_WORK_ITEM_ID, factory=_FACTORY)
    _ = _reading_module()

    target = resolve_dispatch_factory_target(
        args=argparse.Namespace(factory=None),
        repo=tmp_path,
        work_item_id=_WORK_ITEM_ID,
    )

    assert target.name == _FACTORY
    assert target.server == _REGISTRY_SERVER


def test_the_registry_path_is_the_override_when_it_is_set_and_the_default_otherwise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LIVESPEC_FABRO_FACTORY_REGISTRY` wins when non-empty; else the host path.

    The two absent spellings — unset and empty — are asserted together because
    they must answer identically: an implementation testing only for the key's
    presence would read the empty string as a path and resolve nothing, which is
    the same observable as a registry that holds no entry.

    Each absent case asserts the negative beside the constant: with the variable
    not selecting the override file, the resolution must NOT return that file's
    address. The constant alone is an echo; the negative is what an
    implementation reading the override unconditionally cannot satisfy.

    The negative reads the real host `/etc/livespec/fabro-factories.json`, which
    is unmanaged state this suite does not own, so what keeps it hermetic is
    `_REGISTRY_SERVER` being a RESERVED-domain sentinel no inventory can render —
    not an assumption about what that file happens to hold. Spelled as a machine
    this fleet provisions, the assertion is false on exactly the host the
    registry maps `petri` on, which is a false FAIL rather than a finding.
    """
    reading = _reading_module()
    _registry_backed_repo(cwd=tmp_path, monkeypatch=monkeypatch, entry={"server": _REGISTRY_SERVER})

    assert reading.registry_path() == str(tmp_path / "fabro-factories.json")
    assert resolve_fabro_factory(cwd=tmp_path, factory=_FACTORY).server == _REGISTRY_SERVER

    for absent in (None, ""):
        if absent is None:
            monkeypatch.delenv(_REGISTRY_PATH_ENV_VAR, raising=False)
        else:
            monkeypatch.setenv(_REGISTRY_PATH_ENV_VAR, absent)

        assert reading.registry_path() == _SPEC_DEFAULT_REGISTRY_PATH
        assert reading.DEFAULT_REGISTRY_PATH == _SPEC_DEFAULT_REGISTRY_PATH
        assert resolve_fabro_factory(cwd=tmp_path, factory=_FACTORY).server != _REGISTRY_SERVER


# The two faults more than one state is refused for, spelled once. Each mirrors
# the reading's own message, so a row asserts the fault rather than a paraphrase
# of it.
_NO_OBJECT_ENTRY = f"it holds no object entry named {_FACTORY!r}"
_NO_USABLE_SERVER = (
    f"its {_FACTORY!r} entry gives no `server` string that is non-empty after trimming"
)


@pytest.mark.parametrize(
    ("case", "payload", "fault"),
    [
        ("absent", None, "it is absent or unreadable (FileNotFoundError)"),
        ("unreadable", "directory", "it is absent or unreadable (IsADirectoryError)"),
        ("not-json", "{", "it does not parse as JSON"),
        (
            "top-level-list",
            [{_FACTORY: {"server": _REGISTRY_SERVER}}],
            "its top-level value is not an object",
        ),
        ("no-entry", {"legacy": {"server": _OTHER_SERVER}}, _NO_OBJECT_ENTRY),
        ("entry-not-an-object", {_FACTORY: "a-server-string"}, _NO_OBJECT_ENTRY),
        ("entry-without-server", {_FACTORY: {"docker_host": "ssh://host"}}, _NO_USABLE_SERVER),
        ("server-not-a-string", {_FACTORY: {"server": 32276}}, _NO_USABLE_SERVER),
        ("server-blank-after-trimming", {_FACTORY: {"server": "   "}}, _NO_USABLE_SERVER),
    ],
)
def test_an_unresolvable_registry_refuses_before_any_ledger_write_naming_the_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    case: str,
    payload: object,
    fault: str,
) -> None:
    """Every unresolvable registry state refuses, names both, and writes nothing.

    All nine states are parameterized because they have ONE remedy — fix the
    host registry — and must not fall into several messages or, worse, into the
    silent `server=None` that reads downstream as the ambient local factory.

    Each row also asserts the FAULT it is refused FOR, and that assertion is
    what makes the nine rows nine cases rather than one run nine times. Every
    state names the factory and the registry path and exits the same way, so the
    names-and-exit assertions below hold for any of them and cannot tell them
    apart — a row whose staging silently landed on an adjacent arm would report a
    real refusal for the wrong reason and still pass. `unreadable` is the row
    that happens to: it is staged as a DIRECTORY at the registry path rather than
    by clearing the mode bits, because this suite's own dispatch runs as root and
    a mode-based staging does not refuse root at all — the read succeeds, the
    file parses, and what follows is the `no-entry` refusal, under the
    `unreadable` label. `absent` and `unreadable` are therefore discriminated by
    the `OSError` TYPE the reading reports, which is the only field that differs
    between them, and which a mode-bit staging could not produce. The same rule
    binds any capture or replay demonstrating this arm, not just this suite.

    The refusal must name the FACTORY and the REGISTRY PATH. A dispatch resolves
    its factory from `default_factory`, an explicit flag, the environment or a
    per-item pin, so "a registry-backed factory did not resolve" does not say
    which entry to look at, and the path is the file the operator must fix — and
    which of the two paths was read is itself a configuration question.

    The ledger snapshot is the second half of the clause. An unresolvable
    registry that refused AFTER stamping would satisfy a message-only assertion
    while leaving the row claimed by a dispatch that never placed work.

    "And creates no Fabro run" is read off the SHORT-CIRCUIT rather than off a
    launch stand-in, and the scope of that instrument is worth stating: a
    non-None exit code out of `dispatch_preamble` is what every one of its three
    callers — the single dispatch, the drain and the resume — returns
    immediately, so the command ends before it arms a receiver, admits anything
    or reaches a launcher. What this case does NOT establish is that a launch
    seam handed the same refusal would decline; that claim belongs to whichever
    case drives a whole `dispatcher.main` invocation, and asserting it here off
    a runner this seam never consults would be asserting against the fixture.
    """
    registry = tmp_path / "fabro-factories.json"
    if case == "unreadable":
        registry.mkdir()
    elif case == "not-json":
        _ = registry.write_text("{", encoding="utf-8")
    elif payload is not None:
        _write_registry(path=registry, payload=payload)
    _write_config(
        cwd=tmp_path,
        factories={_FACTORY: {"registry": True}},
        default_factory=_FACTORY,
    )
    _point_at_registry(monkeypatch=monkeypatch, path=registry)
    _seed_item()
    _ = _grade_module()
    before = _item_state()

    result = dispatch_preamble(
        args=argparse.Namespace(fabro_bin=None, janitor=None, journal=None),
        repo=tmp_path,
    )

    refusal = capsys.readouterr().err
    assert _FACTORY in refusal
    assert str(registry) in refusal
    assert fault in refusal
    assert result == (None, _EXIT_PRECONDITION_ERROR)
    assert _item_state() == before


@pytest.mark.parametrize("selection", ["flag", "environment"])
def test_an_explicit_undeclared_factory_refuses_before_claim_or_fabro_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    selection: str,
) -> None:
    """An explicit unknown factory names itself and every declared alternative.

    The flag and environment are the two explicit selection entry points.  They
    share one outcome because the selection precedence is one policy, but each
    row must reach it: a guard reading only ``args.factory`` would leave the
    environment route silently aimed at the local Fabro server.

    The preamble is the whole pre-claim boundary.  Its non-None exit is the
    observable short-circuit proving no admission or launcher can run; the
    item snapshot is the durable half of that guarantee.
    """
    _write_config(
        cwd=tmp_path,
        factories={
            _FACTORY: {"server": _REGISTRY_SERVER},
            "legacy": {"server": _OTHER_SERVER},
        },
        default_factory=_FACTORY,
    )
    _seed_item()
    before = _item_state()
    factory = "hp" if selection == "flag" else None
    if selection == "environment":
        monkeypatch.setenv(_FACTORY_SELECTION_ENV_VAR, "hp")

    result = dispatch_preamble(
        args=argparse.Namespace(factory=factory, fabro_bin=None, janitor=None, journal=None),
        repo=tmp_path,
    )

    refusal = capsys.readouterr().err
    assert result == (None, _EXIT_PRECONDITION_ERROR)
    assert "hp" in refusal
    assert _FACTORY in refusal
    assert "legacy" in refusal
    assert _item_state() == before


def test_a_declared_explicit_factory_selection_is_not_refused(tmp_path: Path) -> None:
    """An explicit name remains valid when the declared table contains it."""
    _write_config(
        cwd=tmp_path,
        factories={_FACTORY: {"server": _REGISTRY_SERVER}},
        default_factory=_FACTORY,
    )
    ledger = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger"
    )

    assert "explicit_factory_selection_refusal" in vars(ledger)
    refusal = cast(
        "Callable[..., str | None]",
        vars(ledger)["explicit_factory_selection_refusal"],
    )(args=argparse.Namespace(factory=_FACTORY), repo=tmp_path)

    assert refusal is None


def test_a_valid_selected_entry_resolves_beside_a_malformed_sibling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the selected entry is validated; another entry's shape is not read.

    The sibling is `null`, which is the shape that would raise rather than
    refuse if the resolution walked the whole table. The clause says the other
    entries "are not validated by that resolution and do not affect it", so a
    registry mid-migration — one entry already rendered, one not — must keep
    serving every factory it does name.
    """
    _write_config(
        cwd=tmp_path,
        factories={_FACTORY: {"registry": True}},
        default_factory=_FACTORY,
    )
    registry = tmp_path / "fabro-factories.json"
    _write_registry(path=registry, payload={_FACTORY: {"server": _REGISTRY_SERVER}, "legacy": None})
    _point_at_registry(monkeypatch=monkeypatch, path=registry)
    grade = _grade_module()

    target = resolve_fabro_factory(cwd=tmp_path, factory=_FACTORY)

    assert target.server == _REGISTRY_SERVER
    assert grade.factory_registry_refusal(factory=target) is None


def test_a_recorded_pin_to_an_undeclared_factory_still_falls_back_to_the_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pin naming an entry `dispatcher.factories` no longer declares is ignored.

    The registry clause explicitly leaves this treatment alone, so it is asserted
    HERE rather than assumed: the fallback has to land on the registry-backed
    default and resolve ITS address, which is the composition the clause adds.
    An implementation that refused an undeclared pin, or that fell back to the
    default name without resolving its registry address, would both read as
    "dispatched to petri" at the name and differ at the only field that decides
    which machine runs the work.
    """
    _registry_backed_repo(cwd=tmp_path, monkeypatch=monkeypatch, entry={"server": _REGISTRY_SERVER})
    _seed_item()
    record_dispatch_factory(path=_store(), work_item_id=_WORK_ITEM_ID, factory="hp")
    _ = _reading_module()

    target = resolve_dispatch_factory_target(
        args=argparse.Namespace(factory=None),
        repo=tmp_path,
        work_item_id=_WORK_ITEM_ID,
    )

    assert target.name == _FACTORY
    assert target.server == _REGISTRY_SERVER


def test_a_resolvable_registry_backed_entry_is_not_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive control for the refusal, and it is load-bearing.

    A grade that convicted EVERY registry-backed entry would satisfy all nine
    unresolvable cases above while making the key impossible to use, and the two
    are indistinguishable at the only surface that reports either: both read as
    "the dispatch was refused naming this factory's registry". The whole
    declaration grade is asserted beside the per-key one, because the
    composition in `_dispatcher_factory_environment` is what the pre-dispatch
    arm actually calls, and a per-key grade nothing composed would satisfy every
    other assertion in this module while refusing nothing at a dispatch.
    """
    _registry_backed_repo(cwd=tmp_path, monkeypatch=monkeypatch, entry={"server": _REGISTRY_SERVER})
    grade = _grade_module()
    target = resolve_fabro_factory(cwd=tmp_path, factory=_FACTORY)

    assert grade.factory_registry_refusal(factory=target) is None
    assert factory_declaration_refusal(factory=target) is None


def test_a_caller_holding_no_factory_target_has_no_registry_to_refuse() -> None:
    """No resolved target is an answer, not a fault.

    The needs-attention and standalone reconcile surfaces build their own
    arguments and never run a dispatch preamble, so they hold no factory. That is
    the pre-clause behaviour — the same reason the `bin` and `environment`
    refusals tolerate it — and a refusal there would reject surfaces that
    dispatch nothing.
    """
    grade = _grade_module()

    assert grade.factory_registry_refusal(factory=None) is None


def test_an_entry_carrying_a_server_and_no_registry_key_keeps_its_meaning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed `server` entry is unchanged, and is never graded as registry-backed.

    The clause says so outright, and `server` remains the supported form for an
    adopter outside this fleet. The registry file here maps the same name to a
    DIFFERENT address, so an implementation that consulted the registry for every
    entry would resolve the wrong machine rather than merely doing extra I/O.
    """
    _write_config(cwd=tmp_path, factories={_FACTORY: {"server": _OTHER_SERVER}})
    registry = tmp_path / "fabro-factories.json"
    _write_registry(path=registry, payload={_FACTORY: {"server": _REGISTRY_SERVER}})
    _point_at_registry(monkeypatch=monkeypatch, path=registry)
    grade = _grade_module()

    target = resolve_fabro_factory(cwd=tmp_path, factory=_FACTORY)

    assert target.server == _OTHER_SERVER
    assert grade.factory_registry_refusal(factory=target) is None


@pytest.mark.parametrize("committed_key", ["server", "docker_host"])
def test_a_registry_backed_entry_carrying_a_committed_address_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    committed_key: str,
) -> None:
    """`"registry": true` beside a committed address refuses, naming the factory.

    The registry here maps `petri` to a VALID address, which is what makes this
    a case about the CONFLICT rather than about an unresolvable registry: an
    implementation that simply preferred one source over the other would resolve
    and dispatch, and whichever source it preferred would be right half the time
    and silently wrong the other half — the committed value naming a machine the
    provisioning has already moved off, or the registry value overruling a
    deliberate committed pin, with nothing in the record to say which happened.

    The refusal names the FACTORY and the conflicting KEY, because the remedy is
    an edit to one line of one entry and the operator has to be told which line.
    The registry path is deliberately NOT asserted here: nothing was read from
    it, so a message quoting it would be reporting a file that had no part in
    the decision.
    """
    _write_config(
        cwd=tmp_path,
        factories={_FACTORY: {"registry": True, committed_key: _OTHER_SERVER}},
        default_factory=_FACTORY,
    )
    registry = tmp_path / "fabro-factories.json"
    _write_registry(path=registry, payload={_FACTORY: {"server": _REGISTRY_SERVER}})
    _point_at_registry(monkeypatch=monkeypatch, path=registry)
    _seed_item()
    _ = _grade_module()
    before = _item_state()

    result = dispatch_preamble(
        args=argparse.Namespace(fabro_bin=None, janitor=None, journal=None),
        repo=tmp_path,
    )

    refusal = capsys.readouterr().err
    assert _FACTORY in refusal
    assert f"dispatcher.factories.{_FACTORY}.{committed_key}" in refusal
    assert result == (None, _EXIT_PRECONDITION_ERROR)
    assert _item_state() == before


def test_a_registry_docker_host_is_the_factorys_container_daemon_address(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A registry entry's `docker_host` addresses that factory's container daemon.

    Asserted at the resolved target AND at the Docker CLI argv the container
    sweep's own port produces, because the field alone is an echo: the address
    has to reach `docker --host` as the GLOBAL option ahead of the verb, which
    is the only position the CLI accepts it in, and a value that landed anywhere
    else would read as a well-formed field while every sweep inventoried the
    reconciling host's own daemon instead of the factory's.
    """
    _registry_backed_repo(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        entry={"server": _REGISTRY_SERVER, "docker_host": _REGISTRY_DOCKER_HOST},
    )
    _ = _reading_module()

    target = resolve_fabro_factory(cwd=tmp_path, factory=_FACTORY)

    assert target.server == _REGISTRY_SERVER
    assert target.docker_host == _REGISTRY_DOCKER_HOST

    runner = _Runner()
    assert target.docker_host is not None
    _ = SandboxContainerPort(
        runner=runner, cwd=tmp_path, docker_host=target.docker_host
    ).inventory()
    argv = runner.argvs[0]

    assert argv[:3] == ["docker", "--host", _REGISTRY_DOCKER_HOST]


def test_a_registry_entry_without_a_docker_host_declares_no_container_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A registry entry carrying only a server declares no container-daemon address.

    This is NOT the cosmetic complement of the case above. None is what makes
    the sweep report that factory's containers as UNOBSERVED, naming it; a
    resolution that substituted any address — the server's host, the empty
    string, the local daemon — would inventory somebody else's containers and
    report a clean sweep of the wrong machine. The committed-entry behaviour the
    `docker_host` field already had is exactly this, and the registry must not
    acquire a different one.
    """
    _registry_backed_repo(cwd=tmp_path, monkeypatch=monkeypatch, entry={"server": _REGISTRY_SERVER})
    _ = _reading_module()

    target = resolve_fabro_factory(cwd=tmp_path, factory=_FACTORY)

    assert target.server == _REGISTRY_SERVER
    assert target.docker_host is None


@pytest.mark.parametrize("docker_host", ["   ", 2375, None, []])
def test_an_unusable_registry_docker_host_is_refused_like_an_invalid_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    docker_host: object,
) -> None:
    """A present-but-unusable `docker_host` refuses, even beside a valid server.

    The server is VALID in every case, which is what makes this a case about the
    `docker_host`: the clause refuses such an entry "like an invalid `server`",
    so the whole entry is unresolvable rather than resolving to a server with no
    daemon — and the difference matters because the serverless-daemon reading is
    a legitimate state a sweep reports, so a build that fell back to it would
    convert a typo into a permanently unobserved factory nobody is told about.

    An explicit `null` and a container shape are parameterized beside the
    whitespace and numeric ones because they are what a JSONC author reaches by
    accident, and because membership rather than truthiness is what decides the
    arm: all four are PRESENT, which is what the clause grades.
    """
    _registry_backed_repo(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        entry={"server": _REGISTRY_SERVER, "docker_host": docker_host},
    )
    _seed_item()
    _ = _grade_module()
    before = _item_state()

    result = dispatch_preamble(
        args=argparse.Namespace(fabro_bin=None, janitor=None, journal=None),
        repo=tmp_path,
    )

    refusal = capsys.readouterr().err
    assert _FACTORY in refusal
    assert str(tmp_path / "fabro-factories.json") in refusal
    assert result == (None, _EXIT_PRECONDITION_ERROR)
    assert _item_state() == before
