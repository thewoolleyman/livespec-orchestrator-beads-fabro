"""The harness settings file the Dispatcher writes into every sandbox.

The overlay already projects `BASH_MAX_TIMEOUT_MS` into the sandbox PROCESS
environment, and it arrives -- run 01M4XWYERJEZ15GNMGHV66CSBY records
`"BASH_MAX_TIMEOUT_MS":"3600000"` in its `run.created` environment. It is
nonetheless NOT the cap the harness obeyed. The sandbox agent starts the Claude
harness with `settingSources: ["user", "project", "local"]`, so the governed
repository's own committed `.claude/settings.json` is loaded inside the sandbox,
and a settings-file `env` value OVERRIDES the same variable inherited from the
process environment. That file's 1200000 ms is what ended that run's two final
Green amends at 1202366 ms and 1203117 ms (work-item bd-ib-rv2jk4).

So the projection that decides the cap is a FILE, and it has to be the `local`
source: measured on the operator host with a 50-second call requesting 90000 ms,
project settings at 30000 ended it, while the same project settings beside a
`.claude/settings.local.json` at 120000 let it complete.

These assertions read the prepare step's script back out of the rendered overlay
by decoding the TOML value the renderer produced, so what is asserted is the
script the sandbox will run rather than a second rendering of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

# Opaque non-secret placeholders: the overlay renders whatever it is handed, and
# a literal spelled like a credential at the call site reads to the lint rule as
# a hardcoded one.
_FAKE_TOKEN = "overlay-token-placeholder"
_FAKE_GITHUB_TOKEN = "overlay-github-placeholder"

_WORKFLOW_TOML = '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "sandbox"\n'

# The `local` settings source, spelled as a LITERAL rather than imported: this
# module's Red predates the module that exports it, and a Red's test bytes are
# fixed across its Red-to-Green pair. The binding assertion below ties the two.
_SETTINGS_PATH = "/workspace/.claude/settings.local.json"

# The two ceilings, as they must appear inside the file's `env` object. Spelled
# as the JSON member text rather than as a parsed dict so a mis-nested object
# cannot satisfy the assertion.
_DEFAULT_TIMEOUT_MEMBER = '"BASH_DEFAULT_TIMEOUT_MS": "600000"'
_MAX_TIMEOUT_MEMBER = '"BASH_MAX_TIMEOUT_MS": "3600000"'

_SCRIPT_PREFIX = 'script = "'

_GITHUB_APP_ENV_KEYS = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_API_URL",
)


@pytest.fixture(autouse=True)
def _clear_github_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep overlay assertions independent from factory credential injection.

    The same fixture the sibling overlay tests carry, for the same reason: the
    refreshing `gh` projection reads these keys from the AMBIENT environment, so
    inside a factory sandbox the rendered overlay would otherwise carry a live
    GitHub App private key into every index this file's assertion output reaches.
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


def _prepare_scripts(*, overlay: str) -> tuple[str, ...]:
    """Every `[[run.prepare.steps]]` script the overlay declares, decoded.

    Each renderer writes its script as a TOML BASIC string, which is the shape
    `json.dumps` produces, so one `json.loads` per value recovers the exact bytes
    the sandbox shell receives. The two renderers that use a TOML multi-line
    LITERAL string open with `script = '''` and are therefore outside this
    prefix; neither writes the settings file, so skipping them loses nothing
    here.
    """
    return tuple(
        json.loads(line[len("script = ") :])
        for line in overlay.splitlines()
        if line.startswith(_SCRIPT_PREFIX)
    )


def _settings_writers(*, overlay: str) -> tuple[str, ...]:
    """The decoded scripts that RUN the settings write, not merely name the path.

    The worktree exclusion rendered beside the write names the same path, so a
    filter on the path alone would count two steps and could not tell which of
    them carries the ceilings. Keying on the interpreter the write runs under is
    what discriminates them.
    """
    return tuple(
        script
        for script in _prepare_scripts(overlay=overlay)
        if _SETTINGS_PATH in script and "python3" in script
    )


def test_an_ordinary_dispatch_overlay_writes_the_harness_settings_file(
    tmp_path: Path,
) -> None:
    """One step, writing the local settings file, carrying both ceilings.

    EXACTLY ONE is load-bearing rather than tidy: the step is a write of a whole
    JSON document, so a second copy would run the merge twice and make the file
    the harness reads depend on which step ran last.
    """
    writers = _settings_writers(overlay=_ordinary_overlay(tmp_path=tmp_path))
    assert len(writers) == 1
    assert _DEFAULT_TIMEOUT_MEMBER in writers[0]
    assert _MAX_TIMEOUT_MEMBER in writers[0]
