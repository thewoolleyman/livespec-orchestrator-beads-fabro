"""Which `dispatcher.factories` entry is the configured default, env excluded.

The leaf `_config.resolve_fabro_factory` asks once its own argument and
environment layers decline, and `_dispatcher_overflow_factories` asks with no
layers at all. Both readers get one answer from one place, which is the whole
reason this derivation is a module rather than a private helper restated twice.

Every case here is about a block that NAMES something unusable, because that is
where the two possible answers diverge: returning the declared-but-undeclared
name would resolve to a `FactoryTarget` with no server, and every downstream
surface reads an absent server as the AMBIENT LOCAL Fabro — a dispatch created
on the wrong machine with the item's record naming a factory the work never
reached.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._factory_default import (
    IMPLICIT_FACTORY_NAME,
    configured_factory_name,
)

_DECLARED = "hp"
_SERVER = "https://hp.example.ts.net:32276"


def _block(*, default_factory: object = None, factories: object = None) -> dict[str, Any]:
    """A dispatcher block carrying only the keys a case is about."""
    block: dict[str, Any] = {}
    if default_factory is not None:
        block["default_factory"] = default_factory
    if factories is not None:
        block["factories"] = factories
    return block


def test_a_declared_default_naming_a_declared_entry_is_the_default() -> None:
    """The positive control: without it every case below is satisfied by a constant.

    A reader that returned the implicit name unconditionally would pass all four
    negatives, so this case is what makes them mean anything.
    """
    block = _block(default_factory=_DECLARED, factories={_DECLARED: {"server": _SERVER}})

    assert configured_factory_name(block=block) == _DECLARED


def test_every_block_naming_no_usable_default_resolves_the_implicit_target() -> None:
    """Four unusable blocks, one answer, and the answer is a NAME not a `None`.

    The four are asserted together because they must agree: each one is a
    repository that has named no default, and a reader that distinguished them
    would make the candidate list's first entry depend on which way an operator
    failed to declare one. The `factories`-shaped-wrong case is the one most
    easily simplified away — a `default_factory` that names an entry of
    something that is not a table has still named nothing resolvable.
    """
    unusable = (
        _block(),
        _block(default_factory=_DECLARED),
        _block(default_factory=_DECLARED, factories=[_DECLARED]),
        _block(default_factory="ghost", factories={_DECLARED: {"server": _SERVER}}),
    )

    assert [configured_factory_name(block=one) for one in unusable] == [
        IMPLICIT_FACTORY_NAME for _ in unusable
    ]


def test_a_default_factory_that_is_not_a_non_empty_string_names_nothing() -> None:
    """A key holding a non-string, or the empty string, has declared no name.

    The empty string is in here rather than left to the type test because it IS
    a string: a reader testing only the type would carry `""` forward as a
    factory name, and `has_fabro_factory` would then be asked about an entry
    nobody can declare.
    """
    factories = {_DECLARED: {"server": _SERVER}}

    assert configured_factory_name(block=_block(default_factory="", factories=factories)) == (
        IMPLICIT_FACTORY_NAME
    )
    assert configured_factory_name(block=_block(default_factory=3, factories=factories)) == (
        IMPLICIT_FACTORY_NAME
    )
