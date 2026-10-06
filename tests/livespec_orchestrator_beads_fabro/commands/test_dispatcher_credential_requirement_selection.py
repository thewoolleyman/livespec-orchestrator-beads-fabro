"""The operator surfaces can be pointed at the selection a dispatch will make.

WHAT THIS BINDS, and why the sibling `_surfaces` module is not enough. That
module proves status and manual renewal grade against the SAME requirement
dispatch uses -- for the DEFAULT workflow and the REPOSITORY-level review-fix
cap. That is the common case and it is genuinely the same figure. But a dispatch
can select a registered VARIANT, and a per-item `review-fix-cap:<n>` label can
raise the rendered loop bound above the repository default, and in both of those
cases the operator surfaces were reporting a figure for a DIFFERENT selection
than the dispatch they were being used to predict.

That gap is not closed by documenting it. An operator runs `codex-cred-status`
precisely to answer "will the next dispatch be admitted?", and a status that
silently answers for the reserved workflow while the next dispatch runs a longer
variant gives a confidently wrong answer -- the same class of defect as the
fixed five-hour budget this whole surface replaced, one level up. So the two
commands take explicit selection context and resolve the requirement FOR that
selection.

WHY EACH CASE IS A COMPARISON RATHER THAN A NUMBER. The figures come from the
production derivation over fixtures, so a literal would assert whatever the
derivation happens to produce. Each case instead asserts a RELATION between two
resolutions that differ in exactly one input, which is the only shape that can
distinguish "the context was read" from "the context was accepted and ignored".
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_codex_auth
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    run_codex_cred_status,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    operator_credential_requirement,
)

_NOW = 1_700_000_000

_RESERVED_DIR = ".fabro/workflows/implement-work-item"
_SLOW_DIR = ".fabro/workflows/slow-work-item"

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.checkpoint]
commit_timeout = "10m"
"""


def _graph(*, stages: int) -> str:
    """A chain of `stages` bounded nodes, so a longer variant costs more.

    LENGTH is the dimension varied, not the per-node `timeout` attribute. The
    derivation resolves each node's duration from the dispatch target's
    configured node-timeout policy rather than from the attribute written in the
    graph, so two graphs differing only in a declared `timeout=` resolve the
    SAME allowance -- measured while writing these cases, and worth recording
    because a fixture varying that attribute looks like it should work and then
    asserts nothing. Adding a node adds a visit the derivation does count.
    """
    nodes = "\n".join(f'    stage{index} [timeout="1800s"]' for index in range(stages))
    chain = "\n".join(
        ["    start -> stage0"]
        + [f"    stage{index} -> stage{index + 1}" for index in range(stages - 1)]
        + [f"    stage{stages - 1} -> exit"]
    )
    return (
        "digraph Fixture {\n"
        "    graph [\n"
        "        default_max_retries=0\n"
        '        stall_timeout="7200s"\n'
        "    ]\n"
        "\n"
        "    start [shape=Mdiamond]\n"
        "    exit  [shape=Msquare]\n"
        "\n"
        f"{nodes}\n"
        "\n"
        f"{chain}\n"
        "}\n"
    )


# The review loop the shipped graph guards on `inputs.review_fix_visit_cap`, so a
# raised cap has to widen the derived allowance rather than merely be accepted.
_CAP_GUARDED_GRAPH = """digraph Fixture {
    graph [
        default_max_retries=0
        stall_timeout="7200s"
    ]

    start [shape=Mdiamond]
    exit  [shape=Msquare]

    review [
        timeout="1800s"
    ]

    fix [
        timeout="1800s"
    ]

    start -> review
    review -> fix [condition="outcome=failed && \
context.internal.node_visit_count < {{ inputs.review_fix_visit_cap }}"]
    review -> exit
    fix -> review
}
"""


def _repo(
    *,
    tmp_path: Path,
    block: dict[str, Any] | None = None,
    reserved_graph: str | None = None,
    slow_graph: str | None = None,
) -> Path:
    """A target carrying the reserved workflow and, optionally, a `slow` variant."""
    reserved = tmp_path / _RESERVED_DIR
    reserved.mkdir(parents=True, exist_ok=True)
    _ = (reserved / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (reserved / "workflow.fabro").write_text(
        reserved_graph if reserved_graph is not None else _graph(stages=1),
        encoding="utf-8",
    )
    dispatcher: dict[str, Any] = {} if block is None else dict(block)
    if slow_graph is not None:
        slow = tmp_path / _SLOW_DIR
        slow.mkdir(parents=True, exist_ok=True)
        _ = (slow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
        _ = (slow / "workflow.fabro").write_text(slow_graph, encoding="utf-8")
        dispatcher["workflows"] = {"slow": _SLOW_DIR}
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    return tmp_path


def _required(*, outcome: Any) -> int:
    assert hasattr(outcome, "required_seconds"), outcome
    return outcome.required_seconds


def test_a_named_variant_resolves_that_variants_requirement_not_the_reserved_one(
    tmp_path: Path,
) -> None:
    """Naming the variant a dispatch will select resolves THAT graph's floor.

    The variant's graph is a LONGER CHAIN than the reserved one, so the
    comparison isolates the selection: if `workflow_name` were accepted and
    ignored, both readings would return the reserved graph's figure and be equal.
    """
    repo = _repo(tmp_path=tmp_path, slow_graph=_graph(stages=3))

    reserved = operator_credential_requirement(repo=repo)
    slow = operator_credential_requirement(repo=repo, workflow_name="slow")

    assert _required(outcome=slow) > _required(outcome=reserved)


def test_an_explicit_review_fix_cap_raises_the_operator_requirement(
    tmp_path: Path,
) -> None:
    """A label-raised cap is reportable, because it is what the dispatch renders.

    The graph guards its review loop on `inputs.review_fix_visit_cap`, so a
    larger cap admits more visits and a larger allowance. Without the explicit
    context an operator holding a labelled item could only read the repository
    default and would under-report the floor that item's dispatch is graded
    against.
    """
    repo = _repo(tmp_path=tmp_path, reserved_graph=_CAP_GUARDED_GRAPH)

    default = operator_credential_requirement(repo=repo)
    labelled = operator_credential_requirement(repo=repo, review_fix_cap=9)

    assert _required(outcome=labelled) > _required(outcome=default)


def test_the_detail_names_the_cap_the_reading_took(tmp_path: Path) -> None:
    """The reading says WHICH cap it used, so two figures can be reconciled.

    An operator comparing a status reading against a dispatch refusal for a
    labelled item needs to see whether the two read the same cap; a bare number
    cannot tell them, which is why the inputs are named rather than summarized.
    """
    repo = _repo(tmp_path=tmp_path, reserved_graph=_CAP_GUARDED_GRAPH)

    labelled = operator_credential_requirement(repo=repo, review_fix_cap=9)

    assert hasattr(labelled, "detail"), labelled
    # The cap-to-guard conversion is +1 (the initial review visit plus the fix
    # rounds under it), spelled once in production and read here rather than
    # restated, so the two cannot drift by one.
    assert "review_fix_visit_cap=10" in labelled.detail


def test_an_unregistered_named_variant_still_defers_rather_than_guessing(
    tmp_path: Path,
) -> None:
    """Explicit context does not weaken the fail-closed rule.

    The control against a selection parameter that made the surface permissive:
    naming a variant the registry does not define must still refuse to size it
    off the reserved graph, exactly as the dispatch path does.
    """
    repo = _repo(tmp_path=tmp_path)

    outcome = operator_credential_requirement(repo=repo, workflow_name="not-registered")

    assert not hasattr(outcome, "required_seconds"), outcome
    message = outcome if isinstance(outcome, str) else outcome.message
    assert "not-registered" in message


def test_the_status_command_reports_the_named_variants_requirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The flag reaches the resolver, read off what the OPERATOR is told.

    The cases above exercise the resolver directly, which proves the parameter
    works and says nothing about whether the command passes it. This one drives
    `run_codex_cred_status` twice over one repository -- once plain, once naming
    the longer variant -- and compares the figures in the emitted payloads, so a
    command that declared the flag and dropped it would fail here while every
    resolver-level case still passed.
    """
    repo = _repo(tmp_path=tmp_path, slow_graph=_graph(stages=3))
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "read_host_codex_auth", lambda: _auth_json(exp=_NOW + 10)
    )
    monkeypatch.setattr(_dispatcher_codex_auth.time, "time", lambda: _NOW)

    def _message(*, workflow_name: str | None) -> str:
        _ = run_codex_cred_status(
            args=argparse.Namespace(
                as_json=True,
                observe_identity_state=None,
                workflow_name=workflow_name,
                review_fix_cap=None,
            )
        )
        payload: dict[str, Any] = json.loads(capsys.readouterr().out)
        return str(payload["message"])

    reserved_message = _message(workflow_name=None)
    slow_message = _message(workflow_name="slow")

    reserved = operator_credential_requirement(repo=repo)
    slow = operator_credential_requirement(repo=repo, workflow_name="slow")
    assert str(_required(outcome=reserved)) in reserved_message
    assert str(_required(outcome=slow)) in slow_message
    assert reserved_message != slow_message


def _auth_json(*, exp: int) -> str:
    """A host credential whose access-token JWT carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": f"header.{payload}.sig", "refresh_token": "r"},
        }
    )
