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

THE ENV TABLE ALONE IS NOT ENOUGH, which is what the settings-file assertions
below add. The table arrives — hp run 01M4XWYERJEZ15GNMGHV66CSBY records
`BASH_MAX_TIMEOUT_MS=3600000` in its own `run.created` environment — and is then
overridden one layer down: the sandbox agent starts the Claude harness with
`settingSources: ["user", "project", "local"]`, so the governed repository's
committed `.claude/settings.json` is loaded as the `project` source, and a
settings-file `env` value outranks the same variable inherited from the process
environment. This repository's committed file caps `BASH_MAX_TIMEOUT_MS` at
1200000 ms, so that was the EFFECTIVE cap and two runs lost their Green amend to
it at ~1202 s (`bd-ib-rv2jk4`). The Dispatcher therefore also writes the `local`
source, which outranks `project`, leaving the committed file alone.
"""

from __future__ import annotations

import importlib
import json
import shlex
from pathlib import Path
from typing import Any

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
# The harness's own defaults are 120000 ms for a foreground call and a 600000 ms
# CAP on anything a model asks for, so raising the default to the old cap and the
# cap to an hour is what lets a call that honestly needs 20 minutes declare it.
_BASH_DEFAULT_TIMEOUT_MS = "600000"
_BASH_MAX_TIMEOUT_MS = "3600000"
_BASH_DEFAULT_TIMEOUT_ENV_LINE = f'BASH_DEFAULT_TIMEOUT_MS = "{_BASH_DEFAULT_TIMEOUT_MS}"\n'
_BASH_MAX_TIMEOUT_ENV_LINE = f'BASH_MAX_TIMEOUT_MS = "{_BASH_MAX_TIMEOUT_MS}"\n'
# The `local` settings source the sandbox agent loads AFTER the committed
# `project` one, so this is the file that decides the effective cap. Spelled as
# the suffix RELATIVE to the run's own checkout root, because that root is what
# the harness resolves both of its file-based sources against: an absolute
# `/workspace` spelling names a file no harness opens, and the step that wrote
# one exited 0 while the committed cap stayed in force (bd-ib-rv2jk4).
_SETTINGS_LOCAL_PATH = ".claude/settings.local.json"
_RAISED_TIMEOUT_ENV_LINES = (_BASH_DEFAULT_TIMEOUT_ENV_LINE, _BASH_MAX_TIMEOUT_ENV_LINE)
_HARNESS_SHELL_ENV_LINES = (_NO_AUTO_BACKGROUND_ENV_LINE, *_RAISED_TIMEOUT_ENV_LINES)

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


def test_the_harness_shell_env_helper_renders_the_raised_shell_timeouts() -> None:
    """Both ceilings, spelled once each, in the same named helper.

    The switch above stops a timed-out call from eating the turn; these two are
    what let a call that honestly needs twenty minutes ASK for twenty minutes
    instead of being timed out at the harness's two-minute default.
    """
    module = importlib.import_module(_OVERLAY_MODULE)
    rendered: str = module.harness_shell_env_lines()
    for line in _RAISED_TIMEOUT_ENV_LINES:
        assert rendered.count(line) == 1


def test_an_ordinary_dispatch_overlay_raises_the_harness_shell_timeouts(
    tmp_path: Path,
) -> None:
    """Both ceilings reach an ordinary dispatch's sandbox environment."""
    rendered = _ordinary_overlay(tmp_path=tmp_path)
    for line in _RAISED_TIMEOUT_ENV_LINES:
        assert rendered.count(line) == 1
        assert rendered.index(line) > rendered.index(_ENV_TABLE_HEADER)


def test_a_resume_overlay_raises_the_harness_shell_timeouts(tmp_path: Path) -> None:
    """And the recovery path's, which is the run most likely to need them."""
    rendered = _resume_overlay(tmp_path=tmp_path)
    for line in _RAISED_TIMEOUT_ENV_LINES:
        assert rendered.count(line) == 1
        assert rendered.index(line) > rendered.index(_ENV_TABLE_HEADER)


def _settings_steps(*, rendered: str) -> list[str]:
    """Every prepare step in `rendered` whose script writes the settings file.

    Resolved by PARSING the overlay rather than by counting a substring: the
    block's own comment names the path too, so a substring count would report
    two steps where there is one — and the count is what tells a single
    projection apart from a duplicated one.

    `tomli`, not the stdlib `tomllib`: this suite runs on 3.10, where the stdlib
    module does not exist yet.
    """
    import tomli

    parsed: dict[str, Any] = tomli.loads(rendered)
    steps: list[dict[str, str]] = parsed["run"]["prepare"]["steps"]
    return [step["script"] for step in steps if _SETTINGS_LOCAL_PATH in step["script"]]


def _settings_env(*, rendered: str) -> dict[str, str]:
    """The env mapping the settings-writing step is HANDED, as one shell word.

    Read by tokenizing the script the way a shell does and decoding its last
    argument, so this establishes what the writer program actually receives
    rather than that the digits appear somewhere in the overlay.
    """
    scripts = _settings_steps(rendered=rendered)
    assert len(scripts) == 1, scripts
    decoded: dict[str, str] = json.loads(shlex.split(scripts[0])[-1])
    return decoded


def test_an_ordinary_dispatch_overlay_writes_the_sandbox_harness_settings_file(
    tmp_path: Path,
) -> None:
    """One step, naming the `local` settings source, carrying both ceilings.

    The env table above is necessary and not sufficient: the committed project
    settings outrank it, so without this step the sandbox's effective cap is
    whatever the governed repository committed for its interactive sessions.
    """
    rendered = _ordinary_overlay(tmp_path=tmp_path)
    settings_env = _settings_env(rendered=rendered)
    assert settings_env["BASH_DEFAULT_TIMEOUT_MS"] == _BASH_DEFAULT_TIMEOUT_MS
    assert settings_env["BASH_MAX_TIMEOUT_MS"] == _BASH_MAX_TIMEOUT_MS


def test_a_resume_overlay_writes_the_sandbox_harness_settings_file_exactly_once(
    tmp_path: Path,
) -> None:
    """The recovery path too — and once, for the module docstring's reason.

    A resumed run is precisely the run whose predecessor may already have lost a
    turn to the cap this step raises, so a projection covering only the ordinary
    path would leave the recovery path broken by exactly the fault it recovers
    from.
    """
    rendered = _resume_overlay(tmp_path=tmp_path)
    assert f"refs/heads/{_RESUME_BRANCH}" in rendered
    assert len(_settings_steps(rendered=rendered)) == 1
    settings_env = _settings_env(rendered=rendered)
    assert settings_env["BASH_DEFAULT_TIMEOUT_MS"] == _BASH_DEFAULT_TIMEOUT_MS
    assert settings_env["BASH_MAX_TIMEOUT_MS"] == _BASH_MAX_TIMEOUT_MS


def test_a_changed_env_table_ceiling_changes_the_settings_file_ceiling_too(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ONE tuple renders BOTH layers, so the two cannot disagree.

    This is the assertion that makes the settings file a projection of the env
    table rather than a second, independently-maintained copy of the same
    numbers. A settings file that said something the env table did not would be
    the original fault one layer down — and it would be invisible, because both
    layers would be individually well-formed and each would pass its own test
    above.

    The tuple is reached by NAME through `monkeypatch`, which is this suite's
    sanctioned way of binding a module's own constant, and the env-table
    assertion beside the settings one is the positive control: it shows the
    substitution actually took, so a settings file that happened to match for
    some other reason cannot pass this.
    """
    changed_max = "2700000"
    assert changed_max != _BASH_MAX_TIMEOUT_MS
    module = importlib.import_module(_OVERLAY_MODULE)
    monkeypatch.setattr(
        module,
        "_HARNESS_SHELL_ENV",
        (
            ("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", "1"),
            ("BASH_DEFAULT_TIMEOUT_MS", _BASH_DEFAULT_TIMEOUT_MS),
            ("BASH_MAX_TIMEOUT_MS", changed_max),
        ),
    )
    rendered = _ordinary_overlay(tmp_path=tmp_path)
    assert f'BASH_MAX_TIMEOUT_MS = "{changed_max}"\n' in rendered
    settings_env = _settings_env(rendered=rendered)
    assert settings_env["BASH_MAX_TIMEOUT_MS"] == changed_max
    assert settings_env["BASH_DEFAULT_TIMEOUT_MS"] == _BASH_DEFAULT_TIMEOUT_MS


def test_both_overlay_shapes_carry_the_three_lines_once_beside_tmux_tmpdir(
    tmp_path: Path,
) -> None:
    """The whole projection, asserted as ONE shape across both dispatch shapes.

    Separate from the per-key tests above because this is the assertion that
    would catch a THIRD overlay path rendering a second copy, or one of the
    three being dropped while the other two still pass their own test. The
    TMUX_TMPDIR line is the anchor: it is the env-table neighbour these three
    were added beside, so asserting all four together says the projection landed
    in that table rather than merely somewhere in the file.
    """
    for rendered in (_ordinary_overlay(tmp_path=tmp_path), _resume_overlay(tmp_path=tmp_path)):
        env_table_at = rendered.index(_ENV_TABLE_HEADER)
        for line in (_TMUX_TMPDIR_ENV_LINE, *_HARNESS_SHELL_ENV_LINES):
            assert rendered.count(line) == 1
            assert rendered.index(line) > env_table_at
