"""What the sandbox git-identity steps RENDER as (bd-ib-lsr3vf, Scenario 176).

`tests/integration/test_sandbox_clone_git_identity.py` executes the steps and
asserts that `publish_draft`'s refresh rebase completes, which is the behaviour.
This module asserts the three things about the rendered bytes that an execution
against ONE fixture cannot establish:

- that the pair written into the clone is the SAME resolved author the env table
  projects for the needs_human node's emergency commit, so one run's commits
  cannot be attributed two ways -- asserted over three operator pairs, none of
  them read off a single dispatch;
- that the steps are ones the DISPATCHER renders, so they reach a repository that
  commits its own forked `workflow.toml` and would receive nothing from a step
  written into the bundled one;
- that each value survives the shell, which an execution with a shell-safe
  operator name cannot see at all.

The absent-author case is here for the same reason: a direct caller that resolved
no author policy renders exactly the overlay it did before these steps existed,
and "renders nothing" is a claim about an overlay that cannot be executed.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import (
    GitAuthor,
    git_author_env_lines,
    git_identity_prepare_steps_block,
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
# Three operator pairs: this fleet's own, a name carrying an apostrophe, and one
# carrying a double quote and a space -- the two characters a TOML basic string
# and a shell word respectively would otherwise break on.
_OPERATORS = (
    GitAuthor(name="Chad Woolley", email="thewoolleyman@gmail.com"),
    GitAuthor(name="Dana O'Brien", email="dana@example.invalid"),
    GitAuthor(name='Ada "Tooling" Byng', email="ada@example.invalid"),
)
_MATERIALIZED_MARKER = "# --- Dispatcher-materialized"
_GIT_CONFIG_STEP_RE = re.compile(r'^script = ("git config .*")$', re.MULTILINE)
_AUTHOR_ENV_RE = re.compile(r'^(LIVESPEC_GIT_AUTHOR_(?:NAME|EMAIL)) = (".*")$', re.MULTILINE)
# The two config KEYS this block owns. Selecting on the key rather than on the
# `--local` scope is what leaves the scope assertable: the sibling credential
# helper block also renders a `git config` step, so an unfiltered reading mixes
# it in, while a reading filtered on `--local` would report a `--global` write as
# no write at all.
_IDENTITY_KEYS = ("user.name", "user.email")


def test_the_rendered_steps_write_the_author_into_the_repository_local_config(
    tmp_path: Path,
) -> None:
    """Both keys, in the `--local` scope, for any operator pair.

    The argv is asserted rather than the script string, because the QUOTING is
    `shlex.quote`'s own business -- it quotes only what a shell would otherwise
    read, so a name of shell-safe characters renders bare. Pinning the string
    would fail on a pair whose quoting differs while the config it writes is
    identical.

    `--local` is asserted because the scope decides whether the node that commits
    can read it: a `--global` write lands in the sandbox user's home, which the
    clone's own config lookup reaches but which a committed `.gitconfig` in a
    governed repository could shadow, and a `--system` write needs privileges the
    prepare chain is not guaranteed.
    """
    for author in _OPERATORS:
        rendered = _rendered(tmp_path=tmp_path, author=author)
        assert _materialized_git_config_argv(rendered=rendered) == [
            ["git", "config", "--local", "user.name", author.name],
            ["git", "config", "--local", "user.email", author.email],
        ]


def test_the_configured_pair_is_the_pair_the_env_table_projects(tmp_path: Path) -> None:
    """ONE resolved author reaches the config AND the needs_human node's env.

    The needs_human terminal commits with `LIVESPEC_GIT_AUTHOR_NAME` as the author
    and takes its committer from the clone's config, so a renderer projecting one
    pair into the env table and a different one into the config would attribute
    that single commit two ways -- and nothing in either projection, read alone,
    would show it.
    """
    for author in _OPERATORS:
        rendered = _rendered(tmp_path=tmp_path, author=author)
        argv = _materialized_git_config_argv(rendered=rendered)
        projected = _projected_author_env(rendered=rendered)

        assert argv[0][-1] == projected["LIVESPEC_GIT_AUTHOR_NAME"]
        assert argv[1][-1] == projected["LIVESPEC_GIT_AUTHOR_EMAIL"]


def test_the_identity_steps_are_rendered_before_every_other_materialized_block(
    tmp_path: Path,
) -> None:
    """They are rendered second, immediately after the dispatch-base fetch.

    Every later step and every node that commits has to find the clone already
    carrying a committer, and that ordering is invisible to a case that executes
    one step. The dispatch base keeps the first position because the fetch
    completes the committed `git fetch --unshallow` it follows.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        prepare_inputs={"default_branch": "trunk"},
        git_author=_OPERATORS[0],
    )

    assert rendered is not None
    blocks = _materialized_block_headlines(rendered=rendered)
    assert blocks[0].startswith("# --- Dispatcher-materialized dispatch-base fetch")
    assert blocks[1].startswith("# --- Dispatcher-materialized sandbox git identity")


def test_a_caller_resolving_no_author_renders_no_identity_step(tmp_path: Path) -> None:
    """No author, no steps -- and the rest of the overlay is untouched.

    The second assertion is what says the absence is this block's and not a
    refusal of the whole overlay.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
    )

    assert rendered is not None
    assert _materialized_git_config_argv(rendered=rendered) == []
    assert _MATERIALIZED_MARKER in rendered


def test_the_block_renderer_itself_returns_nothing_for_an_absent_author() -> None:
    """The absent-input arm, read at its own surface rather than through the overlay.

    `git_author_env_lines` has the same arm and the two must agree: a dispatch
    that projected a config pair while projecting no env pair, or the reverse,
    would leave exactly one of the two commit positions without an identity.
    """
    assert git_identity_prepare_steps_block(author=None) == ""
    assert git_author_env_lines(author=None) == ""


def _rendered(*, tmp_path: Path, author: GitAuthor) -> str:
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        git_author=author,
    )
    assert rendered is not None
    return rendered


def _materialized_git_config_argv(*, rendered: str) -> list[list[str]]:
    """Every identity `git config` step the DISPATCHER rendered, as a shell ARGV.

    Scoped to the materialized region so a committed step cannot be mistaken for a
    rendered one -- which is the claim that makes the steps reach a repository
    carrying its own forked run config -- and scoped to the two identity KEYS so
    the sibling credential-helper step is not counted as one of them.
    """
    materialized = rendered[rendered.index(_MATERIALIZED_MARKER) :]
    argv: list[list[str]] = []
    for literal in _GIT_CONFIG_STEP_RE.findall(materialized):
        script = json.loads(literal)
        assert isinstance(script, str)
        tokens = shlex.split(script)
        if any(token in _IDENTITY_KEYS for token in tokens):
            argv.append(tokens)
    return argv


def _materialized_block_headlines(*, rendered: str) -> list[str]:
    """The opening comment line of each Dispatcher-materialized block, in order."""
    materialized = rendered[rendered.index(_MATERIALIZED_MARKER) :]
    return [line for line in materialized.splitlines() if line.startswith(_MATERIALIZED_MARKER)]


def _projected_author_env(*, rendered: str) -> dict[str, str]:
    """The two `LIVESPEC_GIT_AUTHOR_*` values off the rendered env table."""
    projected = {name: json.loads(literal) for name, literal in _AUTHOR_ENV_RE.findall(rendered)}
    assert sorted(projected) == ["LIVESPEC_GIT_AUTHOR_EMAIL", "LIVESPEC_GIT_AUTHOR_NAME"]
    return projected
