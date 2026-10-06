"""The Codex freshness floor, sized against the workflow the dispatch will run.

WHAT THIS BINDS. The dispatch freshness gate used to demand a FIXED five hours
-- a four-hour `implement` node ceiling standing in for the whole run, plus the
documented one-hour margin -- so a repository that raised a node timeout, or
that ran a longer graph, was graded against a figure its own configuration had
already outgrown. These cases bind the replacement: the requirement is the
SELECTED workflow's own resolved execution allowance plus that same documented
margin, and it MOVES when the configuration behind it moves.

WHY TWO OF THESE READ THE SHIPPED WORKFLOW AND THE REST DO NOT. The cases that
assert a DERIVATION -- a raised node timeout raising the requirement, a retry
budget widening it, an unbounded graph refusing -- drive fixtures, because the
shipped graph changes and an assertion against a number read off it would fail
for a graph edit that is not a defect. The two cases that read the real
committed workflow assert only that the resolution REACHES a finite answer over
real syntax and that the answer is no longer the retired constant, which is the
control that would catch this whole surface quietly refusing every dispatch in
this repository.

THE POSITIVE CONTROL IS NOT OPTIONAL HERE. A requirement nothing can satisfy
passes an only-when assertion vacuously, so one case asserts that the shipped
configuration still ADMITS a sufficiently fresh credential through the ordinary
grade, and names the lifetime it admits at.
"""

from __future__ import annotations

import base64
import importlib
import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_freshness import graded_freshness
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_DEADLINE_MODULE = f"{_PACKAGE}._dispatcher_credential_deadline"
_REQUIREMENT_MODULE = f"{_PACKAGE}._dispatcher_credential_requirement"
_COMMANDS_DIR = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_DEADLINE_PATH = _COMMANDS_DIR / "_dispatcher_credential_deadline.py"
_REQUIREMENT_PATH = _COMMANDS_DIR / "_dispatcher_credential_requirement.py"
_SHIPPED_WORKFLOW = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)

# The retired fixed figure: a four-hour run budget plus the one-hour margin.
# Named here so one case can assert the requirement is no longer it.
_RETIRED_REQUIREMENT_SECONDS = 18_000

_FIXTURE_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run]
goal = "fixture"

[run.inputs]
loop_cap = 3

[run.checkpoint]
commit_timeout = "10m"
"""

# One retrying node, one node bounded by an edge guard the `[run.inputs]` table
# above resolves, and one terminal. Deliberately small: every case below that
# drives it asserts a RELATION between two resolutions of it, never a number.
_FIXTURE_GRAPH = """digraph Fixture {
    graph [
        default_max_retries=0
        stall_timeout="7200s"
    ]

    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]

    work [
        timeout="1800s"
    ]

    loop [
        timeout="1800s"
    ]

    start -> work
    work -> loop [label="again", condition="outcome!=succeeded && \
context.internal.node_visit_count < {{ inputs.loop_cap }}"]
    work -> exit
    loop -> work
}
"""


def _write_repo(
    *,
    tmp_path: Path,
    block: dict[str, Any] | None = None,
    workflow_toml: str = _FIXTURE_WORKFLOW_TOML,
    graph: str = _FIXTURE_GRAPH,
    directory: str = ".fabro/workflows/implement-work-item",
) -> Path:
    """A dispatch target carrying one workflow directory and one config block."""
    workflow_dir = tmp_path / directory
    workflow_dir.mkdir(parents=True, exist_ok=True)
    _ = (workflow_dir / "workflow.toml").write_text(workflow_toml, encoding="utf-8")
    _ = (workflow_dir / "workflow.fabro").write_text(graph, encoding="utf-8")
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {} if block is None else block}}
        ),
        encoding="utf-8",
    )
    return tmp_path


def _resolve(
    *,
    repo: Path,
    workflow_name: str | None = None,
    workflow_override: str | None = None,
) -> Any:
    module = importlib.import_module(_REQUIREMENT_MODULE)
    return module.resolve_credential_lifetime_requirement(
        repo=repo,
        workflow_override=workflow_override,
        workflow_name=workflow_name,
    )


def _access_token(*, exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def _auth_json(*, exp: int) -> str:
    return json.dumps({"tokens": {"access_token": _access_token(exp=exp), "refresh_token": "r"}})


def test_the_requirement_is_the_workflow_allowance_plus_the_documented_margin(
    tmp_path: Path,
) -> None:
    """`required_seconds` is the resolved allowance plus the documented margin.

    The FIRST assertion is the module's own existence, so this case fails on an
    assertion rather than at import while the module is absent.
    """
    assert _DEADLINE_PATH.is_file(), "the credential-deadline module is not written yet"
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    resolved = _resolve(repo=_write_repo(tmp_path=tmp_path))
    assert not isinstance(resolved, str), resolved
    assert resolved.margin_seconds == CODEX_FRESHNESS_MARGIN_SECONDS
    assert resolved.required_seconds == resolved.allowance_seconds + CODEX_FRESHNESS_MARGIN_SECONDS
    # The allowance is the GRAPH's, so it has to exceed the single node timeout
    # the fixture declares; a requirement equal to one node's ceiling is the
    # defect this surface replaces.
    assert resolved.allowance_seconds > 1800


def test_a_larger_configured_node_timeout_raises_the_requirement(tmp_path: Path) -> None:
    """A repository that raises a node timeout is graded against the larger figure."""
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    default = _resolve(repo=_write_repo(tmp_path=tmp_path / "default"))
    raised = _resolve(
        repo=_write_repo(
            tmp_path=tmp_path / "raised",
            block={"node_timeouts": {"work": 7200}},
        )
    )
    assert not isinstance(default, str), default
    assert not isinstance(raised, str), raised
    assert raised.required_seconds > default.required_seconds


def test_a_wider_retry_budget_raises_the_requirement(tmp_path: Path) -> None:
    """A node's retry budget multiplies its wall clock, so it moves the floor.

    This is the assertion a fixed allowance cannot make: the retired constant
    was indifferent to every bounded retry the graph declares.
    """
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    without = _resolve(repo=_write_repo(tmp_path=tmp_path / "without"))
    with_retries = _resolve(
        repo=_write_repo(
            tmp_path=tmp_path / "with",
            graph=_FIXTURE_GRAPH.replace(
                'timeout="1800s"\n    ]', 'timeout="1800s"\n' "        max_retries=1\n    ]"
            ),
        )
    )
    assert not isinstance(without, str), without
    assert not isinstance(with_retries, str), with_retries
    assert with_retries.required_seconds > without.required_seconds


def test_an_unbounded_graph_is_refused_rather_than_given_a_default(tmp_path: Path) -> None:
    """A cycle nothing bounds refuses truthfully instead of inventing a figure."""
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    unguarded = _FIXTURE_GRAPH.replace(
        '[label="again", condition="outcome!=succeeded && '
        'context.internal.node_visit_count < {{ inputs.loop_cap }}"]',
        '[label="again"]',
    )
    refusal = _resolve(repo=_write_repo(tmp_path=tmp_path, graph=unguarded))
    assert isinstance(refusal, str), refusal
    assert "credential" in refusal
    assert "workflow" in refusal


def test_an_unregistered_variant_is_refused_rather_than_sized_off_the_reserved_graph(
    tmp_path: Path,
) -> None:
    """An unknown variant's bounds are unknown, and saying so is the only honesty.

    Silently sizing an unregistered variant against the reserved graph would
    present the reserved graph's allowance as that variant's maximum.

    The refusal is a `WorkflowFaultDeferral` rather than a bare string, and THIS
    CASE ORIGINALLY ASSERTED THE BARE STRING -- worth recording, because that
    assertion is what let the credential wall answer an unregistered variant as
    its own refusal. The wall runs early, so it answered first and
    `workflow-variant-unregistered` -- a real journal stage that names the
    variant and writes an outcome record -- never spoke, which is how a registry
    fault came to produce no outcome record at all. What this case actually cares
    about is unchanged and still asserted: NO requirement is returned, and the
    message names the variant. Which surface gets to refuse is the registry
    stage's business, and the type is what carries that.
    """
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    module = importlib.import_module(_REQUIREMENT_MODULE)
    refusal = _resolve(repo=_write_repo(tmp_path=tmp_path), workflow_name="groom-slice")
    assert isinstance(refusal, module.WorkflowFaultDeferral), refusal
    assert "groom-slice" in refusal.message


def test_the_shipped_workflow_resolves_to_a_finite_requirement_above_the_retired_one(
    tmp_path: Path,
) -> None:
    """This repository's own committed workflow resolves, and not to the old five hours.

    The control against a parser that quietly fails on the one graph this
    factory actually runs, and against a requirement that silently stayed the
    retired constant.
    """
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    shipped = _write_repo(
        tmp_path=tmp_path,
        workflow_toml=_SHIPPED_WORKFLOW.read_text(encoding="utf-8"),
        graph=_SHIPPED_WORKFLOW.with_name("workflow.fabro").read_text(encoding="utf-8"),
    )
    resolved = _resolve(repo=shipped)
    assert not isinstance(resolved, str), resolved
    assert resolved.required_seconds != _RETIRED_REQUIREMENT_SECONDS
    assert resolved.required_seconds > _RETIRED_REQUIREMENT_SECONDS


def test_the_dispatch_grade_takes_the_resolved_allowance_rather_than_a_constant() -> None:
    """`graded_freshness` grades against a budget its caller resolved.

    The signature is asserted first because that is the whole claim: a grade
    reading a module constant cannot be made to follow a repository's own
    configuration, however the configuration moves.
    """
    assert "run_budget_seconds" in inspect.signature(graded_freshness).parameters
    now = 1_000_000
    verdict = graded_freshness(
        source_auth_json=_auth_json(exp=now + 200_000),
        now_epoch=now,
        run_budget_seconds=100_000,
    )
    assert verdict is not None
    assert verdict.required_remaining_seconds == 100_000 + CODEX_FRESHNESS_MARGIN_SECONDS
    assert verdict.fresh_enough is True


def test_a_sufficiently_fresh_credential_is_still_admitted_under_the_shipped_requirement(
    tmp_path: Path,
) -> None:
    """The positive control: the shipped configuration still admits a fresh credential.

    An implementation that always refused, or always reported an unknown bound,
    would satisfy every refusal case above and deliver nothing. This names the
    lifetime at which the shipped requirement admits.
    """
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    shipped = _write_repo(
        tmp_path=tmp_path,
        workflow_toml=_SHIPPED_WORKFLOW.read_text(encoding="utf-8"),
        graph=_SHIPPED_WORKFLOW.with_name("workflow.fabro").read_text(encoding="utf-8"),
    )
    resolved = _resolve(repo=shipped)
    assert not isinstance(resolved, str), resolved
    now = 1_000_000
    admitted = graded_freshness(
        source_auth_json=_auth_json(exp=now + resolved.required_seconds),
        now_epoch=now,
        run_budget_seconds=resolved.allowance_seconds,
    )
    assert admitted is not None
    assert admitted.fresh_enough is True
    # And one second short of it does not pass, so the boundary is the figure
    # above rather than a floor anything below it also clears.
    refused = graded_freshness(
        source_auth_json=_auth_json(exp=now + resolved.required_seconds - 1),
        now_epoch=now,
        run_budget_seconds=resolved.allowance_seconds,
    )
    assert refused is not None
    assert refused.fresh_enough is False


def test_the_absolute_deadline_is_anchored_at_projection_not_at_the_first_node() -> None:
    """The enforced deadline is the projection instant plus the allowance.

    Anchoring it at projection is what makes queue and preparation delay count
    AGAINST the budget instead of silently extending it.
    """
    assert _DEADLINE_PATH.is_file(), "the credential-deadline module is not written yet"
    module = importlib.import_module(_DEADLINE_MODULE)
    assert (
        module.credential_use_deadline_epoch(projected_epoch=1_000, allowance_seconds=60) == 1_060
    )
    assert module.credential_use_remaining_seconds(deadline_epoch=1_060, now_epoch=1_000) == 60
    # Aged by queueing: the same deadline, less of it left.
    assert module.credential_use_remaining_seconds(deadline_epoch=1_060, now_epoch=1_050) == 10


# Every entry declares `[run.checkpoint] commit_timeout = "10m"` on THIS
# repository's own shipped run config, differing only in TOML spelling. The ids
# name the spelling so a failure says which one regressed.
_CHECKPOINT_SPELLINGS = [
    pytest.param('commit_timeout = "10m"', id="canonical"),
    pytest.param('    commit_timeout = "10m"', id="indented-assignment"),
    pytest.param("commit_timeout = '10m'", id="literal-string"),
    pytest.param('commit_timeout = "10m"  # checkpoint budget', id="trailing-comment"),
    pytest.param('"commit_timeout" = "10m"', id="quoted-key"),
]


@pytest.mark.parametrize("spelling", _CHECKPOINT_SPELLINGS)
def test_every_checkpoint_spelling_resolves_the_same_requirement(
    spelling: str, tmp_path: Path
) -> None:
    """The checkpoint declaration's SPELLING cannot move the credential floor.

    Asserted through the LIFETIME RESOLVER rather than against the TOML reader,
    because the reader returning the right string is not the property that
    matters -- the property that matters is that the required lifetime a
    dispatch is graded against does not change when an operator reformats a
    comment. The reader has its own cases in
    `test_dispatcher_toml_read.py`; this is the one that would have caught the
    defect where it hurt.

    The defect this retires: the checkpoint value enters the allowance
    MULTIPLIED BY THREE (the engine spends `commit_timeout` independently on
    `git add`, `git diff --cached` and `git commit`), and a spelling the old
    regex reader did not recognize was reported as ABSENT, so the engine's stock
    thirty seconds silently replaced the configured ten minutes -- and that
    product is billed PER ATTEMPT, so the error scales with the graph. Measured
    on this shipped config and graph: the configured value resolves 588030
    seconds while the absent-reading resolves 324690, an understatement of
    263340 seconds (about 3.05 days), with nothing in the output to say which
    reading had been taken.

    The RELATION is asserted rather than either number, because the shipped
    graph changes and a literal here would fail for a graph edit that is not a
    defect. A mutation check confirmed these cases FAIL against a reader
    restricted to the canonical spelling, so the equivalence is measured rather
    than assumed.
    """
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    shipped = _SHIPPED_WORKFLOW.read_text(encoding="utf-8")
    assert 'commit_timeout = "10m"' in shipped, "the shipped config no longer declares the budget"
    graph = _SHIPPED_WORKFLOW.with_name("workflow.fabro").read_text(encoding="utf-8")

    canonical = _resolve(
        repo=_write_repo(tmp_path=tmp_path / "canonical", workflow_toml=shipped, graph=graph)
    )
    respelled = _resolve(
        repo=_write_repo(
            tmp_path=tmp_path / "respelled",
            workflow_toml=shipped.replace('commit_timeout = "10m"', spelling),
            graph=graph,
        )
    )

    assert not isinstance(canonical, str), canonical
    assert not isinstance(respelled, str), respelled
    assert respelled.required_seconds == canonical.required_seconds


def test_a_declared_checkpoint_budget_that_is_not_a_duration_refuses_rather_than_defaulting(
    tmp_path: Path,
) -> None:
    """A declared-but-unusable budget refuses; it does not become the stock default.

    The control for the case above. Both readings produce a well-formed number,
    so without this case a build that silently defaulted every unrecognized
    declaration would satisfy the equivalence assertion by resolving them all to
    the same WRONG figure.
    """
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    shipped = _SHIPPED_WORKFLOW.read_text(encoding="utf-8")
    graph = _SHIPPED_WORKFLOW.with_name("workflow.fabro").read_text(encoding="utf-8")

    refusal = _resolve(
        repo=_write_repo(
            tmp_path=tmp_path,
            workflow_toml=shipped.replace('commit_timeout = "10m"', "commit_timeout = 600"),
            graph=graph,
        )
    )

    assert isinstance(refusal, str), refusal
    assert "commit_timeout" in refusal
    assert "stock budget is NOT used in its place" in refusal
