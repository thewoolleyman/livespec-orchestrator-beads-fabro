"""What the dispatch-base fetch RENDERS as (bd-ib-xlblgr, Scenario 61).

`test_dispatcher_default_branch_fetch` executes the step and asserts the diff
resolves, which is the behaviour. This module asserts the three things about the
rendered bytes that an execution against ONE fixture cannot establish:

- that the branch is PROJECTED from the integration contract's own input rather
  than spelled, which is the "for every repository and not only for
  livespec-orchestrator-beads-fabro" half of the work-item -- asserted over three
  default-branch names, none of them read off a single dispatch;
- that the step is one the DISPATCHER renders, so it reaches a repository that
  commits its own forked `workflow.toml` and would receive nothing from a step
  written into the bundled one;
- that it is rendered BEFORE every other Dispatcher-materialized block, which no
  single-step execution can see at all.

The absent-projection case is here for the same reason: a direct caller that wires
no contract inputs renders exactly the overlay it did before this step existed, and
"renders nothing" is a claim about an overlay that cannot be executed.

The expected input NAME is read back off `CONTRACT_INPUT_NAMES` rather than spelled
`default_branch` twice: that mapping is the closed set of fields that cross into
the sandbox, and a renderer keyed on a name the projection does not carry would
render for no dispatch while reading perfectly here.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch_fetch import (
    default_branch_fetch_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    CONTRACT_INPUT_NAMES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    DEFAULT_BRANCH_FIELD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
_OAUTH_TOKEN = "oauth-token-value-that-must-not-leak"
_GITHUB_TOKEN = "github-token-value-that-must-not-leak"
# Three default-branch names, none of them this fleet's own `master`: an adopter on
# `main`, an adopter on `trunk`, and a namespaced branch whose slashes the refspec
# has to carry on both halves.
_DEFAULT_BRANCHES = ("main", "trunk", "release/stable")
_MATERIALIZED_MARKER = "# --- Dispatcher-materialized"
_FETCH_STEP_RE = re.compile(r'^script = ("git fetch .*")$', re.MULTILINE)


def test_the_rendered_step_fetches_the_projected_branch_into_a_tracking_ref(
    tmp_path: Path,
) -> None:
    """The refspec names the projected branch on BOTH halves, for any branch name.

    The destination half is the load-bearing one: measured 2026-10-14, a bare
    `git fetch origin <branch>` in a single-branch clone writes `FETCH_HEAD` and
    creates no `refs/remotes/origin/<branch>`, exiting 0 with no warning. A step
    carrying only the source half would therefore read as a correct fetch.
    """
    for default_branch in _DEFAULT_BRANCHES:
        rendered = _rendered(tmp_path=tmp_path, default_branch=default_branch)
        assert _materialized_fetch_argv(rendered=rendered) == [
            [
                "git",
                "fetch",
                "--quiet",
                "origin",
                f"+refs/heads/{default_branch}:refs/remotes/origin/{default_branch}",
            ]
        ]


def test_the_projected_input_name_is_the_contract_input_the_sandbox_receives(
    tmp_path: Path,
) -> None:
    """The step reads the SAME input name the prompts and `--input` pairs read.

    Keyed on anything else, the renderer would render for no dispatch at all while
    every assertion taken against a hand-built mapping still passed.
    """
    name = CONTRACT_INPUT_NAMES[DEFAULT_BRANCH_FIELD.attribute]

    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        prepare_inputs={name: "trunk"},
    )

    assert rendered is not None
    assert _materialized_fetch_argv(rendered=rendered) == [
        ["git", "fetch", "--quiet", "origin", "+refs/heads/trunk:refs/remotes/origin/trunk"]
    ]


def test_the_dispatch_base_fetch_precedes_every_other_materialized_block(
    tmp_path: Path,
) -> None:
    """It is rendered FIRST among the Dispatcher's own steps.

    The committed chain's `git fetch --unshallow` is what the step completes, so it
    belongs immediately after it -- which is the first materialized position. Any
    later one leaves the blocks between the two running against a clone with no
    dispatch base, and that ordering is invisible to a case that executes one step.
    """
    rendered = _rendered(tmp_path=tmp_path, default_branch="trunk")
    materialized = rendered[rendered.index(_MATERIALIZED_MARKER) :]

    assert materialized.startswith(
        "# --- Dispatcher-materialized dispatch-base fetch: bring the governed"
    )


def test_a_caller_projecting_no_default_branch_renders_no_step(tmp_path: Path) -> None:
    """No projection, no step -- and the rest of the overlay is untouched.

    A direct caller that wires no contract inputs renders exactly the overlay it
    rendered before this step existed. The second assertion is what says the
    absence is this block's and not a refusal of the whole overlay.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
    )

    assert rendered is not None
    assert _materialized_fetch_argv(rendered=rendered) == []
    assert _MATERIALIZED_MARKER in rendered


def test_a_projected_default_branch_of_whitespace_renders_no_step() -> None:
    """An unresolvable branch renders nothing rather than a refspec of whitespace.

    `git fetch origin '+refs/heads/:refs/remotes/origin/'` is a step that fails in
    preparation naming a refspec nobody wrote, which reads as a broken Dispatcher
    rather than as the absent default branch it is.
    """
    assert default_branch_fetch_prepare_steps_block(prepare_inputs={"default_branch": "  "}) == ""


def _rendered(*, tmp_path: Path, default_branch: str) -> str:
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        prepare_inputs={"default_branch": default_branch},
    )
    assert rendered is not None
    return rendered


def _materialized_fetch_argv(*, rendered: str) -> list[list[str]]:
    """Every `git fetch` step the DISPATCHER rendered, as the ARGV a shell receives.

    Scoped to the materialized region so a committed step cannot be mistaken for a
    rendered one -- which is the claim that makes the step reach a repository
    carrying its own forked run config.

    Each script is decoded from its TOML basic string and then TOKENIZED, because
    the argv is what decides which ref is fetched and where it lands, while the
    QUOTING is `shlex.quote`'s own business: it quotes only what a shell would
    otherwise read, so a refspec of shell-safe characters renders bare. Asserting
    the string would pin that decision and fail on a branch name whose quoting
    differs while the fetch it performs is identical.
    """
    materialized = rendered[rendered.index(_MATERIALIZED_MARKER) :]
    argv: list[list[str]] = []
    for literal in _FETCH_STEP_RE.findall(materialized):
        script = json.loads(literal)
        assert isinstance(script, str)
        argv.append(shlex.split(script))
    return argv
