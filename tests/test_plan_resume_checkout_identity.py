"""The plan-resume fixtures resolve their `required_result` repository by checkout.

Work-item `bd-ib-w4kuh6`. The plan-resume suites resolved their `required_result`
repository by CHECKOUT DIRECTORY NAME, so they passed from the primary clone and
failed from every secondary checkout — a worktree under
`~/.worktrees/<repo>/<branch>`, and the Dispatcher's own post-merge janitor
checkout `~/.worktrees/<repo>/janitor-<item>`. Master CI stayed green throughout,
so the suites reported a defect that existed only in the checkout the operator
and the janitor were standing in.

Two assertions carry that, and each needs the OTHER checkout to mean anything:

- A required_result built against a BRANCH-NAMED checkout resolves THERE, and the
  repository's own declared name does NOT. The second half is the control: both
  arms run against the same directory with the same configuration, so the only
  thing separating them is which name the reference carries. Without it, "the
  reference resolved" is equally consistent with a resolver that resolves
  everything — which is the one reading that would leave the defect in place.
- `CHECKOUT_UNDER_TEST` is the checkout this suite is running from, and the
  reference built against it resolves to that root AND answers with that root's
  own tenant connection. Resolution owes both halves: a reference that read the
  right configuration while executing in the wrong directory would read one
  repository's `.livespec.jsonc` and ask another repository's ledger.

The third case is the adoption question — whether the three fixtures actually
take this derivation — and it is the only one of the three that can fire from the
primary clone, which is where every author runs the suite. It asserts the
positive (each fixture imports the shared derivation) BESIDE the absence of the
declared repository name, read from `.claude-plugin/plugin.json` rather than
written here: the literal is the exact token whose presence was the defect, so a
fixture that imports the helper and then hardcodes the name anyway is still
caught.
"""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    resolve_result_repository,
    result_store_config,
)

from tests.plan_resume_checkout import CHECKOUT_UNDER_TEST, item_status_result

if TYPE_CHECKING:
    from pathlib import Path

# A directory name a secondary checkout really carries: the worktree root names
# each checkout after its branch, never after the repository.
_BRANCH_NAMED = "fabro-bd-ib-w4kuh6"
_PROBE_ITEM = "bd-ib-w4kuh6"

# The three plan-resume fixtures whose required_result named the repository
# literally, relative to the checkout they live in.
_PLAN_RESUME_FIXTURES: tuple[str, ...] = (
    "tests/integration/test_plan_next_action_resume_scenario111.py",
    "tests/livespec_orchestrator_beads_fabro/commands/test_plan_next_action.py",
    "tests/livespec_orchestrator_beads_fabro/commands/test_plan_resume_definition_of_done_gap.py",
)

_SHARED_DERIVATION_IMPORT = "from tests.plan_resume_checkout import"


def _declared_repository_name() -> str:
    """This repository's own name, as its plugin manifest declares it."""
    manifest = json.loads(
        (CHECKOUT_UNDER_TEST / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    name = manifest["name"]
    assert isinstance(name, str)
    return name


def _reference_repository(*, checkout: Path) -> str:
    repo = item_status_result(checkout=checkout, item_id=_PROBE_ITEM, status="closed")["repo"]
    assert isinstance(repo, str)
    return repo


def test_a_branch_named_checkout_resolves_the_fixture_reference_but_not_the_literal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    branch_named = tmp_path / _BRANCH_NAMED
    branch_named.mkdir()
    _ = shutil.copy(CHECKOUT_UNDER_TEST / ".livespec.jsonc", branch_named)

    resolved = resolve_result_repository(
        project_root=branch_named,
        name=_reference_repository(checkout=branch_named),
    )

    assert resolved is not None
    assert resolved.clone == branch_named
    config = result_store_config(repository=resolved)
    assert config is not None
    assert config.repo_root == branch_named
    # The control: the same directory, the same configuration, the literal name.
    assert (
        resolve_result_repository(
            project_root=branch_named,
            name=_declared_repository_name(),
        )
        is None
    )


def test_the_fixture_reference_resolves_to_the_checkout_under_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")

    resolved = resolve_result_repository(
        project_root=CHECKOUT_UNDER_TEST,
        name=_reference_repository(checkout=CHECKOUT_UNDER_TEST),
    )

    assert resolved is not None
    assert resolved.clone == CHECKOUT_UNDER_TEST
    config = result_store_config(repository=resolved)
    assert config is not None
    assert config.repo_root == CHECKOUT_UNDER_TEST


def test_every_plan_resume_fixture_takes_the_shared_checkout_derivation() -> None:
    declared = _declared_repository_name()
    for relative_path in _PLAN_RESUME_FIXTURES:
        source = (CHECKOUT_UNDER_TEST / relative_path).read_text(encoding="utf-8")
        assert _SHARED_DERIVATION_IMPORT in source, relative_path
        assert declared not in source, relative_path
