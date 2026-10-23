"""The sandbox environment one confirmation turn is PLACED in.

Beside `test_acp_availability_probe_timeout.py`, which binds the clause, and
`test_acp_availability_probe_run_degraded.py`, which covers the readings a
healthy factory never produces. This module covers the one property the probe's
whole equivalence claim rests on and no reading of its OUTCOME can observe:
where the turn ran.

THE CLAUSE NAMES FOUR EXECUTION PROPERTIES and the module docstring argues only
the first three. "Availability is confirmed only by a successfully completed ACP
prompt turn using the candidate's pinned adapter version, requested model and
effort, and projected worker credential identity." The adapter bytes are argued
from `render_adapter`; the credential identity is a property of the SANDBOX,
which the factory's declared `environment` selects out of the server's catalog —
so a probe that omits the flag runs in the server's DEFAULT environment and the
turn's credential identity is not the dispatch's.

BOTH OUTCOMES OF THAT OMISSION ARE WRONG, which is why the positive case is worth
a module. With no credential in the default environment, no healthy provider can
ever earn a confirmation and the post-expiry stall the probe exists to end
persists unchanged and silently. With one, the turn confirms a credential
identity nobody dispatches with — the "confirm a model nobody ran" failure
`availability_probe_refusal` turns an in-protocol candidate away to avoid,
arriving through the placement instead of through `config_options`.

THE UNDECLARED CASE IS THE CONTROL AND IS NOT OPTIONAL. A build emitting the flag
unconditionally satisfies the positive case exactly as well, and
`fabro_run_argv`'s own note records what that costs: pinned 0.254 has no such
flag and selects from `workflow.toml`, so an unconditional pair kills every
dispatch to that engine at argument parsing, before any run exists to diagnose.

THE DECLARED VALUE IS ASSERTED AGAINST `factory_environment_id` RATHER THAN
AGAINST A TRANSCRIBED CONSTANT, because what the clause asks for is that the
probe and a dispatch to the same factory agree about where they ran — and a
transcribed expectation agrees with the dispatch path only for as long as nobody
changes the shared grading. Measured while authoring this module: `"   "` is a
USABLE id under `factory_environment_from_entry`, whose test is `value != ""`,
so an expectation asserting a whitespace-only declaration named no environment
would have pinned the probe to a DIVERGENCE from the dispatch path — the one
defect this module exists to close, re-introduced by its own test. The empty
string is the unusable declaration, and it is the one the third case drives.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_RUN_ID = "01M5PROBEENV0000000000000"
_NOW = "2026-10-23T09:15:00Z"
_SERVER = "https://gmktec.example.ts.net:32276"
_ENVIRONMENT = "livespec-ci"


def _config(**entry: str) -> str:
    """One repository config declaring the `petri` factory with `entry`'s keys.

    Rendered rather than pasted so the declared environment and the asserted
    one cannot drift, and built as a mapping so an ABSENT key is the caller
    omitting it rather than a second literal maintained beside the first.
    """
    return json.dumps(
        {
            "livespec-orchestrator-beads-fabro": {
                "dispatcher": {
                    "default_factory": "petri",
                    "factories": {"petri": {"server": _SERVER, **entry}},
                }
            }
        }
    )


@dataclass(kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Engine:
    """A fabro runner that records every argv the probe spends."""

    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> _Command:
        self.calls.append(list(argv))
        _ = (cwd, timeout_seconds, env)
        if "--version" in argv:
            return _Command(exit_code=0, stdout="fabro 0.254.0 (8869e88 2026-10-01)\n")
        if "inspect" in argv or "events" in argv:
            return _Command(exit_code=0, stdout="[]")
        return _Command(exit_code=0, stdout=f"Run: {_RUN_ID}\n")

    def launch_argv(self) -> list[str]:
        """The one `fabro run` argv, which is the only launch a probe spends."""
        launches = [argv for argv in self.calls if "run" in argv]
        assert len(launches) == 1, self.calls
        return launches[0]


def _candidate() -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="claude-code-acp"),
        identity=schema.AcpCandidateIdentity(
            display_name="Claude Opus 5",
            candidate_key="claude-opus-5-high",
            availability_key="anthropic",
        ),
    )


def _probe(*, tmp_path: Path, config: str, engine: _Engine) -> Any:
    _ = (tmp_path / ".livespec.jsonc").write_text(config, encoding="utf-8")
    runner = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_run")
    return runner.run_availability_probe(
        repo=tmp_path,
        candidate=_candidate(),
        builtin=True,
        work_item_id="bd-ib-n3pzcl",
        observation_ids=(),
        now_iso=_NOW,
        timeout_seconds=120,
        runner=engine,
    )


def _dispatch_path_environment(*, repo: Path) -> str | None:
    """What the DISPATCH path would place a run of this repository in.

    Read through the two functions the dispatch path itself composes, so the
    expectation tracks the shared grading instead of transcribing today's
    answer — see the module docstring for what a transcribed one admits.
    """
    config = importlib.import_module(f"{_PACKAGE}._config")
    environment = importlib.import_module(f"{_PACKAGE}._dispatcher_factory_environment")
    return environment.factory_environment_id(factory=config.resolve_fabro_factory(cwd=repo))


def test_the_turn_is_placed_in_the_environment_the_factory_declares(tmp_path: Path) -> None:
    """The probe's sandbox is the dispatch's sandbox, so its credential is too."""
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, config=_config(environment=_ENVIRONMENT), engine=engine)

    assert not isinstance(result, str), result
    argv = engine.launch_argv()
    assert "--environment" in argv, argv
    assert argv[argv.index("--environment") + 1] == _ENVIRONMENT, argv
    # And it is the DISPATCH PATH's own answer rather than a second reading
    # that happens to agree with it today.
    assert argv[argv.index("--environment") + 1] == _dispatch_path_environment(repo=tmp_path)
    # The server is the same factory's, so the placement is not read off some
    # other entry that happened to declare an environment.
    assert argv[argv.index("--server") + 1] == _SERVER, argv


def test_a_factory_declaring_no_environment_spends_no_flag(tmp_path: Path) -> None:
    """The pinned engine has no such flag, so an unconditional pair kills the launch."""
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, config=_config(), engine=engine)

    assert not isinstance(result, str), result
    assert "--environment" not in engine.launch_argv(), engine.calls


def test_an_unusable_declaration_names_no_environment(tmp_path: Path) -> None:
    """`factory_declaration_refusal` has already refused such a dispatch.

    So the id reduces to None here exactly as it does on the dispatch path, and
    the turn carries no flag rather than a blank one the server cannot resolve.
    The control is the assertion BELOW it: this is the dispatch path's reading
    of the same repository, not a stricter one the probe applied on its own.
    """
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, config=_config(environment=""), engine=engine)

    assert not isinstance(result, str), result
    assert "--environment" not in engine.launch_argv(), engine.calls
    assert _dispatch_path_environment(repo=tmp_path) is None
