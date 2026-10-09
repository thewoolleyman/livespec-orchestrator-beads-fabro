"""Every facade verb the Dispatcher calls is exercised by an Enemy Unit Test.

The Enemy Unit Test suite under `fabro-enemy-unit-tests/` is what turns "the
pinned engine still behaves as we assume" into evidence. It only covers the
verbs it actually calls, though, and nothing connected the two sides: the
Dispatcher could start depending on a facade verb no tier module had ever run
against a live factory, and a pinned-versus-candidate comparison would still
come back green having never touched it. Nine verbs were in exactly that state
when this was measured on 2026-10-09 — `answer_question`, `auth_login`,
`bearer_token`, `cancel`, `client_version`, `dump`, `questions`, `server_api`
and `system_info`.

So this module is the binding, and it is deliberately NOT an enemy test: it
spawns nothing and needs no server. It reads the facade's own classes for the
verb universe, the package for which verbs the Dispatcher names, and the tier
modules for which ones the suite runs, then asserts the implication.

THE PRODUCTION SCAN OVER-APPROXIMATES, ON PURPOSE. It keys on the method NAME,
and several verbs here are ordinary names on other objects — `run` on every
command runner, `dump` on `json`, `cancel` on the Codex app-server client. So
the required set is a SUPERSET of the verbs genuinely reached through a port.
That direction is the safe one: it can only ask for more enemy coverage than
is strictly owed, never less. The failure mode worth guarding is the opposite
one — a scan that silently matched nothing would make the implication
vacuously true while printing exactly what full coverage prints — which is
what the positive controls below exclude.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpPort

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro"
_ENEMY_SUITE = _REPO_ROOT / "fabro-enemy-unit-tests"
_CONFTEST = _ENEMY_SUITE / "conftest.py"
_FAMILY_PREFIX = "_fabro_port"

# The two faces of the facade. Both are reached from the Dispatcher — the CLI
# port directly, the server-API port through `FabroPort.server_api()`.
_PORT_CLASSES = (FabroPort, FabroHttpPort)

# POSITIVE CONTROL for the production scan: verbs this repository has called
# for long enough that their disappearance would mean the scan broke, not that
# the Dispatcher stopped calling them.
_CONTROL_REQUIRED = frozenset({"events", "inspect", "ps", "rm", "run"})

# POSITIVE CONTROL for the enemy scan, same reasoning from the other side.
_CONTROL_EXERCISED = frozenset({"inspect", "ps", "run"})

# A verb whose name is ALSO an ordinary verb on something else here. Asserted
# so the over-approximation documented above is acknowledged and measured
# rather than discovered later as a surprise.
_OVER_APPROXIMATED_VERB = "dump"
_OVER_APPROXIMATING_MODULE = "_reflector_runtime.py"


def _port_method_universe() -> frozenset[str]:
    """Every public verb the two facade classes declare."""
    return frozenset(
        name
        for cls in _PORT_CLASSES
        for name, value in vars(cls).items()
        if callable(value) and not name.startswith("_")
    )


def _modules_naming(
    *, root: Path, universe: frozenset[str], skip_family: bool
) -> dict[str, set[str]]:
    """Which files call each universe verb as an attribute, keyed by verb."""
    named: dict[str, set[str]] = {}
    for parent, dirnames, filenames in os.walk(root):
        dirnames[:] = [dirname for dirname in dirnames if dirname != "__pycache__"]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            if skip_family and filename.startswith(_FAMILY_PREFIX):
                continue
            path = Path(parent) / filename
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=filename)):
                match node:
                    case ast.Call(func=ast.Attribute(attr=attr)) if attr in universe:
                        named.setdefault(attr, set()).add(filename)
                    case _:
                        pass
    return named


def _tier_module_paths() -> list[Path]:
    """The suite modules that run against the live factory."""
    return sorted(_ENEMY_SUITE.glob("test_tier*.py"))


def _exercised(*, universe: frozenset[str]) -> dict[str, set[str]]:
    named: dict[str, set[str]] = {}
    for path in _tier_module_paths():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=path.name)):
            match node:
                case ast.Call(func=ast.Attribute(attr=attr)) if attr in universe:
                    named.setdefault(attr, set()).add(path.name)
                case _:
                    pass
    return named


# ---------------------------------------------------------------------------
# The two instruments, before the implication that rides on them.
# ---------------------------------------------------------------------------


def test_the_verb_universe_is_read_off_the_real_facade_classes() -> None:
    universe = _port_method_universe()

    # Non-empty, public-only, and carrying both faces' verbs: a universe read
    # from the wrong place would make both scans match nothing.
    assert universe
    assert not [name for name in universe if name.startswith("_")]
    assert {"run", "dump"} <= universe
    assert {"questions", "system_info"} <= universe


def test_the_enemy_suite_tiers_drive_a_real_server_through_a_real_subprocess() -> None:
    # What makes a tier module's call "against a real server": the shared
    # fixture builds the port from a configured server url and the PRODUCTION
    # subprocess runner, so nothing in either tier is stubbed.
    conftest = _CONFTEST.read_text(encoding="utf-8")

    assert _tier_module_paths()
    assert "FABRO_EUT_SERVER" in conftest
    assert "ShellCommandRunner()" in conftest
    assert "FabroTarget(server_url=config.server_url)" in conftest


def test_the_production_scan_over_approximates_rather_than_under_approximates() -> None:
    universe = _port_method_universe()
    required = _modules_naming(root=_PACKAGE, universe=universe, skip_family=True)

    # The acknowledged over-approximation, measured: `dump` is required partly
    # because a module that never touches Fabro calls something of that name.
    # Recorded as an assertion so the scan's direction is a known property
    # rather than a later surprise.
    assert _OVER_APPROXIMATING_MODULE in required[_OVER_APPROXIMATED_VERB]


# ---------------------------------------------------------------------------
# The implication.
# ---------------------------------------------------------------------------


def test_every_facade_verb_the_dispatcher_calls_is_exercised_against_a_real_server() -> None:
    universe = _port_method_universe()
    required = frozenset(_modules_naming(root=_PACKAGE, universe=universe, skip_family=True))
    exercised = frozenset(_exercised(universe=universe))

    # Both scans report an ABSENCE, so neither verdict is evidence until it is
    # shown each one can return a hit at all.
    assert required >= _CONTROL_REQUIRED
    assert exercised >= _CONTROL_EXERCISED
    assert required <= universe
    assert exercised <= universe

    assert sorted(required - exercised) == []
