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

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_harness_shell_policy
from livespec_orchestrator_beads_fabro.commands._dispatcher_harness_shell_policy import (
    HARNESS_SETTINGS_MARKER,
    SANDBOX_HARNESS_SETTINGS_PATH,
    harness_settings_merge_program,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    ResumeCheckout,
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

_RESUME_BRANCH = "feat/bd-ib-rv2jk4"
_RESUME_HEAD = "a" * 40

# A ceiling no production value equals, so a settings file carrying it can only
# have read the env tuple rather than a literal of its own.
_CHANGED_MAX_TIMEOUT = "2700000"

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


def _resume_overlay(*, tmp_path: Path) -> str:
    """The RECOVERY path's overlay, which is a different dispatch path.

    Asserted beside the ordinary one deliberately: a resumed run is precisely the
    run whose predecessor may already have lost a turn to the cap, so a
    projection covering only the ordinary path would leave the recovery path
    broken by exactly the fault it is recovering from.
    """
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


def test_the_literals_here_are_the_ones_the_policy_module_exports() -> None:
    """Bind this module's spelled literals to the names production renders from.

    The two above are spelled rather than imported because this module's Red
    predates the module that exports them, and a Red's test bytes are fixed
    across its Red-to-Green pair. Without this assertion a later rename would
    leave every case here passing against a path no dispatch writes.
    """
    assert SANDBOX_HARNESS_SETTINGS_PATH == _SETTINGS_PATH
    assert HARNESS_SETTINGS_MARKER == "livespec-sandbox-harness-settings"


def test_a_resume_overlay_writes_the_harness_settings_file_once(tmp_path: Path) -> None:
    """The recovery path carries the same step, once, with the same two ceilings."""
    rendered = _resume_overlay(tmp_path=tmp_path)
    assert f"refs/heads/{_RESUME_BRANCH}" in rendered
    writers = _settings_writers(overlay=rendered)
    assert len(writers) == 1
    assert _DEFAULT_TIMEOUT_MEMBER in writers[0]
    assert _MAX_TIMEOUT_MEMBER in writers[0]


def test_the_settings_file_follows_the_env_table_it_was_rendered_from(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ONE tuple feeds both projections, so they cannot declare different caps.

    This is the assertion that would catch the fix being half-applied -- a
    settings file carrying its own literal copy of the ceilings would satisfy
    every case above and then drift the moment the env table moved, which is the
    two-sources-of-truth fault this work-item exists to close rather than to
    relocate. The changed value is asserted in BOTH projections: in the file
    alone it could have come from a second literal, and in the table alone it
    says nothing about what the harness will read.
    """
    monkeypatch.setattr(
        _dispatcher_harness_shell_policy,
        "_HARNESS_SHELL_ENV",
        (("BASH_MAX_TIMEOUT_MS", _CHANGED_MAX_TIMEOUT),),
    )
    rendered = _ordinary_overlay(tmp_path=tmp_path)
    writers = _settings_writers(overlay=rendered)
    assert len(writers) == 1
    assert f'"BASH_MAX_TIMEOUT_MS": "{_CHANGED_MAX_TIMEOUT}"' in writers[0]
    assert _MAX_TIMEOUT_MEMBER not in writers[0]
    assert f'BASH_MAX_TIMEOUT_MS = "{_CHANGED_MAX_TIMEOUT}"\n' in rendered


def _run_merge_program(
    *,
    target: Path,
    scratch: Path,
    module_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    """Run the SHIPPED merge program against `target` and return what it wrote.

    The program is materialized and imported exactly as the sandbox runs it,
    rather than re-implemented here: a Python transcription of the merge would be
    a second account of it, and the two would diverge in the direction that is
    invisible -- both would look correct and only the one the sandbox runs would
    decide anything. `sys.argv` carries the destination because that is the one
    operand the prepare step's shell hands it.
    """
    fragment = scratch / "fragment.py"
    fragment.write_text(harness_settings_merge_program(), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(fragment), str(target)])
    spec = importlib.util.spec_from_file_location(module_name, fragment)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return json.loads(target.read_text(encoding="utf-8"))


def test_the_merge_program_writes_the_ceilings_into_a_sandbox_carrying_no_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ordinary case: no settings file yet, so the document is the `env` object."""
    document = _run_merge_program(
        target=tmp_path / "settings.local.json",
        scratch=tmp_path,
        module_name="livespec_harness_settings_fragment_absent",
        monkeypatch=monkeypatch,
    )
    assert document["env"] == {
        "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
        "BASH_DEFAULT_TIMEOUT_MS": "600000",
        "BASH_MAX_TIMEOUT_MS": "3600000",
    }


def test_the_merge_program_keeps_every_other_key_a_sandbox_file_already_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A MERGE and not an overwrite, in both directions.

    The other top-level key survives untouched, and an `env` member this
    projection does not name survives beside the one it replaces -- which is
    what tells a merge apart from a write that happens to produce the right
    ceilings.
    """
    target = tmp_path / "settings.local.json"
    target.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash"]},
                "env": {"KEEP_ME": "yes", "BASH_MAX_TIMEOUT_MS": "1200000"},
            }
        ),
        encoding="utf-8",
    )
    document = _run_merge_program(
        target=target,
        scratch=tmp_path,
        module_name="livespec_harness_settings_fragment_merge",
        monkeypatch=monkeypatch,
    )
    assert document["permissions"] == {"allow": ["Bash"]}
    assert document["env"] == {
        "KEEP_ME": "yes",
        "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
        "BASH_DEFAULT_TIMEOUT_MS": "600000",
        "BASH_MAX_TIMEOUT_MS": "3600000",
    }


def test_the_merge_program_reports_a_file_it_could_not_merge_into(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A file holding no JSON object is replaced, and the replacement is ANNOUNCED.

    Refusing instead would fail the prepare step, which kills the run at launch
    before any work is driven -- over a per-sandbox file that no longer parses.
    So the arm writes a fresh document, and the stderr line carrying the
    projection's own marker is what keeps that from being silent.
    """
    target = tmp_path / "settings.local.json"
    target.write_text("not json at all", encoding="utf-8")
    document = _run_merge_program(
        target=target,
        scratch=tmp_path,
        module_name="livespec_harness_settings_fragment_unparseable",
        monkeypatch=monkeypatch,
    )
    assert document["env"] == {
        "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
        "BASH_DEFAULT_TIMEOUT_MS": "600000",
        "BASH_MAX_TIMEOUT_MS": "3600000",
    }
    captured = capsys.readouterr()
    assert f"{HARNESS_SETTINGS_MARKER}: {target} held no JSON object" in captured.err
