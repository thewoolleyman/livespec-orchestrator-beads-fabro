"""Tests for a factory's declared sandbox environment, as READ (bd-ib-fgre25).

On the Petri-era engine the server selects a run's sandbox environment from
the run intent's `environment_id` ALONE: `fabro run` with no `--environment`
sends `default`, and that selection OVERRIDES the `[run.environment]` id the
workflow declares. So a dispatch to a candidate factory landed in the
server's default environment — `buildpack-deps:noble`, no `mise` on PATH —
and the run died in a prepare step with `sh: 1: mise: not found`, reported as
a work-item failure rather than as the placement fault it was.

A factory entry's optional `environment` key carries the catalog id, and this
module covers the READING of it: `_factory_environment` is the leaf `_config`
imports for that one sub-key, exactly as it imports `_node_timeouts` and
`_workflow_variants` for theirs. The GRADE of that reading — the pre-claim
refusal and the id the `fabro run` argv carries — is
`_dispatcher_factory_environment`, covered beside it.

The reading keeps ABSENT and DECLARED-BUT-UNUSABLE apart, which is the whole
point of a two-field record where a `str | None` would read more simply: the
pinned 0.254 engine has no `--environment` flag at all, so a reading that
collapsed a typo onto "declares none" would send the dispatch to the default
environment exactly as before — the failure the key exists to remove,
restored silently by the shape of its own reading.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_factory

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_READING_MODULE = "livespec_orchestrator_beads_fabro.commands._factory_environment"
_CANDIDATE_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32278"
_CATALOG_ENVIRONMENT = "livespec-ci"


def _write_config(*, cwd: Path, dispatcher: dict[str, object]) -> None:
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def _reading_module() -> Any:
    """The reading leaf, imported inside the test body.

    The module path is asserted FIRST so the Red is a genuine assertion
    failure rather than a collection error — at Red the module does not exist,
    and a top-level import of it would die before any assertion ran.
    """
    assert (_COMMANDS_DIR / "_factory_environment.py").is_file()
    return importlib.import_module(_READING_MODULE)


def test_a_factory_entry_accepts_an_optional_environment_naming_a_catalog_id(
    tmp_path: Path,
) -> None:
    """The key is read as written, with absent and unusable kept apart.

    All four readings are asserted together because they are ONE grammar and
    the distinctions only exist relative to each other: a declared id, an
    absent key, an empty string, and a non-string. The last two must report
    `declared` while carrying no id — that pairing is what the grade turns
    into a refusal, and a reading that reported them as absent would leave
    nothing to refuse.

    Each reading is taken twice: once from the entry mapping the leaf grades,
    and once end-to-end through `resolve_fabro_factory` off a committed
    `.livespec.jsonc`. The second is not a duplicate of the first — a leaf
    that reads the key perfectly is worth nothing until the resolved factory
    target actually carries the result.
    """
    reading = _reading_module()

    assert reading.factory_environment_from_entry(
        entry={"environment": _CATALOG_ENVIRONMENT}
    ) == reading.FactoryEnvironment(declared=True, environment_id=_CATALOG_ENVIRONMENT)
    assert reading.factory_environment_from_entry(entry={}) == reading.NO_FACTORY_ENVIRONMENT
    for unusable in ("", 7, None):
        assert reading.factory_environment_from_entry(
            entry={"environment": unusable}
        ) == reading.FactoryEnvironment(declared=True, environment_id=None)

    _write_config(
        cwd=tmp_path,
        dispatcher={
            "factories": {
                "hp-candidate": {"server": _CANDIDATE_SERVER, "environment": _CATALOG_ENVIRONMENT},
                "hp": {"server": _CANDIDATE_SERVER},
                "blank": {"server": _CANDIDATE_SERVER, "environment": ""},
            }
        },
    )

    assert resolve_fabro_factory(
        cwd=tmp_path, factory="hp-candidate"
    ).environment == reading.FactoryEnvironment(declared=True, environment_id=_CATALOG_ENVIRONMENT)
    assert resolve_fabro_factory(cwd=tmp_path, factory="hp").environment == (
        reading.NO_FACTORY_ENVIRONMENT
    )
    assert resolve_fabro_factory(
        cwd=tmp_path, factory="blank"
    ).environment == reading.FactoryEnvironment(declared=True, environment_id=None)
