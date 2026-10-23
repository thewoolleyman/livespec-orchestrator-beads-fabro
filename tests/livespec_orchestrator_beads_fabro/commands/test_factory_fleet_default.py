"""Which factory the registry DESIGNATES as the fleet default, and the refusal.

`fleet_default_reading` is the reading `dispatcher.default_factory: "fleet"`
resolves through, and the grade beside it is what a dispatch whose designation
did not resolve is refused with. Both halves are here because the refusal's
whole content is the reading's `detail`: a case asserting only that some
refusal was produced would pass for an implementation that reported the wrong
fault, and every one of the five unresolvable states has a different remedy.

WHY EVERY UNRESOLVABLE CASE ASSERTS THE DETAIL AND NOT MERELY `name is None`.
The clause requires the refusal to name "the registry path and what it lacked",
and `name is None` is satisfied identically by all five. An operator told only
that no fleet default resolved cannot tell an unprovisioned file from a
designation that points at nothing, and the two are fixed in different places.

WHY THE REFUSAL IS ASSERTED THROUGH A `FactoryTarget` RATHER THAN DIRECTLY.
The refusal is what the pre-claim grade produces from a RESOLVED target, so
reading it off the reading alone would prove that a sentence can be composed
and not that the dispatch path composes it. The target is built through the
production resolution, from a repository committing the reserved value, which
is the one shape the fleet arm is reachable from.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_factory
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_registry import (
    factory_registry_refusal,
    factory_registry_unobservable,
)
from livespec_orchestrator_beads_fabro.commands._factory_default import (
    IMPLICIT_FACTORY_NAME,
    configured_factory_name,
    fleet_selection,
)
from livespec_orchestrator_beads_fabro.commands._factory_registry import (
    FLEET_DEFAULT_FACTORY,
    REGISTRY_DEFAULT_KEY,
    fleet_default_reading,
)

_PETRI = "petri"
_PETRI_SERVER = "https://petri.example:32276"
_REGISTRY_PATH_ENV_VAR = "LIVESPEC_FABRO_FACTORY_REGISTRY"


@pytest.fixture(autouse=True)
def _no_inherited_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither the override nor a factory selection inherited from the dispatch."""
    monkeypatch.delenv(_REGISTRY_PATH_ENV_VAR, raising=False)
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)


def _point_at(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "fabro-factories.json"
    _ = path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(_REGISTRY_PATH_ENV_VAR, str(path))
    return path


def _fleet_block(*, factories: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"default_factory": FLEET_DEFAULT_FACTORY, "factories": factories or {}}


def test_a_designated_factory_resolves_and_refuses_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive control: without it every refusal case passes on a constant."""
    path = _point_at(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        payload={REGISTRY_DEFAULT_KEY: _PETRI, _PETRI: {"server": _PETRI_SERVER}},
    )
    reading = fleet_default_reading()

    assert reading.name == _PETRI
    assert reading.detail is None
    assert reading.path == str(path)
    assert configured_factory_name(block=_fleet_block()) == _PETRI


@pytest.mark.parametrize(
    ("case", "payload", "lacked"),
    [
        (
            "no default key",
            {_PETRI: {"server": _PETRI_SERVER}},
            f"it has no `{REGISTRY_DEFAULT_KEY}` key",
        ),
        (
            "default is not a string",
            {REGISTRY_DEFAULT_KEY: 7, _PETRI: {"server": _PETRI_SERVER}},
            f"its `{REGISTRY_DEFAULT_KEY}` value 7 is not a string non-empty after trimming",
        ),
        (
            "default is blank",
            {REGISTRY_DEFAULT_KEY: "   ", _PETRI: {"server": _PETRI_SERVER}},
            f"its `{REGISTRY_DEFAULT_KEY}` value '   ' is not a string" " non-empty after trimming",
        ),
        (
            "default names no entry",
            {REGISTRY_DEFAULT_KEY: _PETRI},
            f"its `{REGISTRY_DEFAULT_KEY}` names 'petri', which is no factory entry of its own",
        ),
        (
            "default is a factory entry",
            {REGISTRY_DEFAULT_KEY: {"server": _PETRI_SERVER}},
            f"it carries a factory entry named {REGISTRY_DEFAULT_KEY!r}, which is"
            " the reserved fleet-default key and may not name a factory",
        ),
    ],
)
def test_an_unresolvable_designation_names_the_path_and_what_it_lacked(
    case: str,
    payload: dict[str, Any],
    lacked: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each unresolvable state names its own fault, and refuses the dispatch.

    The reserved-key row is the one whose fault cannot be inferred from the
    others: `default` holding an object is a registry that has overwritten its
    own designation with a factory, and reporting it as a malformed value would
    send an operator to write a designation into the key the mistake occupies.
    """
    del case
    path = _point_at(monkeypatch=monkeypatch, tmp_path=tmp_path, payload=payload)
    reading = fleet_default_reading()

    assert reading.name is None
    assert reading.detail == lacked

    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": _fleet_block()}}),
        encoding="utf-8",
    )
    target = resolve_fabro_factory(cwd=tmp_path)
    refusal = factory_registry_refusal(factory=target)

    assert target.name == FLEET_DEFAULT_FACTORY
    assert target.server is None
    assert refusal is not None
    assert str(path) in refusal
    assert lacked in refusal
    assert factory_registry_unobservable(factory=target) is not None


def test_an_unreadable_registry_refuses_rather_than_designating_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent registry file is a refusal, never an absent designation.

    Asserted apart from the five rows above because its detail comes from the
    SHARED table read rather than from the designation grade, so an
    implementation could get every designation fault right and still fall
    through to the implicit target here — which resolves to no server at all
    and is read by every downstream surface as this host's own engine.
    """
    monkeypatch.setenv(_REGISTRY_PATH_ENV_VAR, str(tmp_path / "absent.json"))
    reading = fleet_default_reading()

    assert reading.name is None
    assert reading.detail == "it is absent or unreadable (FileNotFoundError)"
    assert configured_factory_name(block=_fleet_block()) == FLEET_DEFAULT_FACTORY


def test_a_repository_not_naming_the_reserved_value_selects_no_fleet_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`fleet_selection` answers only for the name the reserved value reaches.

    Two negatives beside the positive, because each is a different way the
    reading could leak onto a factory the registry has nothing to say about: a
    repository naming a factory outright, and a fleet repository selecting some
    OTHER factory explicitly — whose committed entry would otherwise be graded
    as registry-backed and refused over a key it never declared.
    """
    _ = _point_at(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        payload={REGISTRY_DEFAULT_KEY: _PETRI, _PETRI: {"server": _PETRI_SERVER}},
    )
    named = {"default_factory": "legacy", "factories": {"legacy": {"server": _PETRI_SERVER}}}

    assert fleet_selection(block=named, name="legacy") is None
    assert configured_factory_name(block=named) == "legacy"
    assert fleet_selection(block=_fleet_block(), name="legacy") is None
    assert fleet_selection(block=_fleet_block(), name=_PETRI) is not None


def test_an_absent_default_factory_keeps_the_implicit_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository declaring no default is unaffected by a registry that exists.

    The clause's own "an ABSENT `dispatcher.default_factory` keeps its existing
    treatment", which is what leaves an adopter outside this fleet alone — and
    the one case a designation-first implementation gets wrong by resolving the
    fleet default for a repository that never asked for it.
    """
    _ = _point_at(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        payload={REGISTRY_DEFAULT_KEY: _PETRI, _PETRI: {"server": _PETRI_SERVER}},
    )

    assert configured_factory_name(block={}) == IMPLICIT_FACTORY_NAME
    assert fleet_selection(block={}, name=IMPLICIT_FACTORY_NAME) is None
