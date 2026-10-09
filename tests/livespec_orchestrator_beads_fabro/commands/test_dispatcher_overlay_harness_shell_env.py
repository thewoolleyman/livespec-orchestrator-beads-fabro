"""The harness shell-tool policy every sandbox agent's environment carries.

The Claude harness moves a foreground shell call that REACHES its timeout into
a background task, and the ACP engine then raises `BackgroundedTool` and ENDS
the turn — so an honest long foreground call (a full pytest run, a coverage
pass) destroys the stage instead of returning late. No agent-side timeout and
no prompt wording can prevent that, because the harness decides it: the only
route is the environment the Dispatcher materializes for the run, which is what
these assertions bind.

The RESUME overlay is asserted beside the ordinary one deliberately. Both are
rendered by one function, but they are reached by different dispatch paths, and
a resumed run is precisely the run whose predecessor may already have lost a
turn this way — so a projection that covered only the ordinary path would leave
the recovery path broken by exactly the fault it is recovering from.

EXACTLY ONCE is load-bearing rather than tidy. The lines land inside the
`[environments.<id>.env]` table, and a duplicate key makes the WHOLE overlay
unparseable TOML — so a second copy does not degrade one dispatch, it fails
every dispatch through the run config, which is why the count is asserted and
not just the presence.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    ResumeCheckout,
)

_OVERLAY_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_overlay"

# Opaque non-secret placeholders: the overlay renders whatever it is handed, and
# a literal spelled like a credential at the call site reads to the lint rule as
# a hardcoded one.
_FAKE_TOKEN = "overlay-token-placeholder"
_FAKE_GITHUB_TOKEN = "overlay-github-placeholder"

_WORKFLOW_TOML = '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "sandbox"\n'
_ENV_TABLE_HEADER = "[environments.sandbox.env]"

_TMUX_TMPDIR_ENV_LINE = 'TMUX_TMPDIR = "/workspace/.tmux"\n'
_NO_AUTO_BACKGROUND_ENV_LINE = 'CLAUDE_CODE_DISABLE_BACKGROUND_TASKS = "1"\n'

_RESUME_BRANCH = "feat/bd-ib-k627ja"
_RESUME_HEAD = "a" * 40

_GITHUB_APP_ENV_KEYS = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_API_URL",
)


@pytest.fixture(autouse=True)
def _clear_github_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep overlay assertions independent from factory credential injection.

    The same fixture `test_config` carries, for the same reason: the refreshing
    `gh` projection reads these keys from the AMBIENT environment, so inside a
    factory sandbox the rendered overlay would otherwise carry a live GitHub App
    private key — into every index this file's assertion output reaches.
    """
    for key in _GITHUB_APP_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _ordinary_overlay(*, tmp_path: Path) -> str:
    rendered = render_run_config_overlay(
        committed_text=_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    return rendered


def _resume_overlay(*, tmp_path: Path) -> str:
    rendered = render_run_config_overlay(
        committed_text=_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        resume_checkout=ResumeCheckout(branch=_RESUME_BRANCH, head=_RESUME_HEAD),
    )
    assert rendered is not None
    return rendered


def test_the_harness_shell_env_helper_renders_the_no_auto_background_switch() -> None:
    """The named helper is the one place the switch is spelled.

    Asserted through the module object rather than a top-level import so this
    reads as a failing ASSERTION before the helper exists, not as a collection
    error that proves only unimportability.
    """
    module = importlib.import_module(_OVERLAY_MODULE)
    assert "harness_shell_env_lines" in module.__all__
    rendered: str = module.harness_shell_env_lines()
    assert rendered.count(_NO_AUTO_BACKGROUND_ENV_LINE) == 1


def test_an_ordinary_dispatch_overlay_disables_harness_auto_backgrounding(
    tmp_path: Path,
) -> None:
    """One line, inside the env table, beside the TMUX_TMPDIR line already there."""
    rendered = _ordinary_overlay(tmp_path=tmp_path)
    assert rendered.count(_NO_AUTO_BACKGROUND_ENV_LINE) == 1
    assert _TMUX_TMPDIR_ENV_LINE in rendered
    assert rendered.index(_NO_AUTO_BACKGROUND_ENV_LINE) > rendered.index(_ENV_TABLE_HEADER)


def test_a_resume_overlay_disables_harness_auto_backgrounding(tmp_path: Path) -> None:
    """The recovery path carries it too — see the module docstring."""
    rendered = _resume_overlay(tmp_path=tmp_path)
    assert f"refs/heads/{_RESUME_BRANCH}" in rendered
    assert rendered.count(_NO_AUTO_BACKGROUND_ENV_LINE) == 1
    assert _TMUX_TMPDIR_ENV_LINE in rendered
    assert rendered.index(_NO_AUTO_BACKGROUND_ENV_LINE) > rendered.index(_ENV_TABLE_HEADER)
