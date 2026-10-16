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

AND IT HAS TO BE THE CLONE ROOT'S COPY OF THAT SOURCE, which is why the
executable cases below exist beside the rendered-text ones. The harness resolves
the `local` source against the PROJECT DIRECTORY, so a file at a fixed
`/workspace/.claude/settings.local.json` is not a settings source at all on a
sandbox whose clone root is somewhere else -- and the clone root is somewhere
else on every layout this fleet has measured. Measured 2026-10-16 inside an hp
sandbox: the clone is `/repos/<owner>/<repo>`, `/workspace/<repo>` is a symlink
to it, a `/workspace/.claude/settings.local.json` holding 3600000 had been on
disk since before the harness started, and a shell tool call still reported
`BASH_MAX_TIMEOUT_MS=1200000` -- the committed project value -- while the same
process environment carried 3600000. The write landed the right bytes at a path
that decided nothing.

A presence assertion over the rendered text cannot tell a path the harness reads
from one it ignores, so the two layouts are BUILT and the rendered steps are RUN
in them: `_prepare_steps` decodes the production renderer's own TOML, so what is
asserted is the script the sandbox will run rather than a second rendering of it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands import _dispatcher_harness_shell_policy
from livespec_orchestrator_beads_fabro.commands._dispatcher_harness_shell_policy import (
    HARNESS_SETTINGS_MARKER,
    harness_settings_merge_program,
    harness_settings_prepare_steps_block,
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

# The `local` settings source, spelled RELATIVE to the clone root -- which is
# what the harness resolves it against, and the only spelling that is true on
# every sandbox layout. The binding assertion below ties it to the production
# constant.
_SETTINGS_RELATIVE_PATH = ".claude/settings.local.json"

# The question both prepare steps ask instead of assuming a layout. Spelled here
# so a step that went back to a fixed prefix fails rather than passing on a path
# no harness reads.
_CLONE_ROOT_RESOLUTION = "git rev-parse --show-toplevel"

# The fixed sandbox root that is NOT the clone root on any measured layout, and
# whose absence from the rendered steps is what this file guards.
_SANDBOX_ROOT = "/workspace"

# The repository's own committed settings source, which the exclusion must leave
# visible to git: `.claude/` is a directory a governed repository legitimately
# tracks.
_COMMITTED_SETTINGS_RELATIVE_PATH = ".claude/settings.json"

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

_DEFAULT_BRANCH = "master"
_STEP_TIMEOUT_SECONDS = 60

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
        if _SETTINGS_RELATIVE_PATH in script and "python3" in script
    )


def _prepare_steps() -> tuple[str, ...]:
    """The policy block's own two steps, in order, decoded through a TOML parser.

    Read from the production renderer rather than sliced out of the whole overlay
    so the executable cases run the exclusion and the write as a PAIR and in the
    order every dispatch runs them.

    The fixed-root assertion lives HERE, in front of every executable case,
    rather than only in the case that measures it: these cases run the real
    scripts, and a step carrying an absolute `/workspace` path would write into
    the REAL sandbox root of whatever factory stage is running this suite.
    """
    document = tomli.loads(harness_settings_prepare_steps_block())
    steps = document["run"]["prepare"]["steps"]
    assert isinstance(steps, list)
    scripts = tuple(str(step["script"]) for step in steps)
    for script in scripts:
        assert _SANDBOX_ROOT not in script
    return scripts


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

    The path is spelled rather than imported, and read back through `getattr`
    rather than at module import, because this module's Red predates the constant
    it binds and a Red's test bytes are fixed across its Red-to-Green pair -- the
    same reason the `test_plan_epoch_*` family gives. Without this assertion a
    later rename would leave every case here passing against a path no dispatch
    writes.
    """
    bound = getattr(
        _dispatcher_harness_shell_policy,
        "SANDBOX_HARNESS_SETTINGS_RELATIVE_PATH",
        None,
    )
    assert bound == _SETTINGS_RELATIVE_PATH
    assert HARNESS_SETTINGS_MARKER == "livespec-sandbox-harness-settings"


def test_neither_prepare_step_assumes_a_fixed_sandbox_path_for_the_settings_source(
    tmp_path: Path,
) -> None:
    """The settings source is RESOLVED, never assumed, on both steps.

    This is the assertion the measured defect needed. A step naming
    `/workspace/.claude/settings.local.json` writes correct bytes to a path the
    harness never loads, and every other case in this file passes on it: the
    ceilings are there, the merge is right, exactly one step writes. Only the
    PATH is wrong, and only against the live sandbox layout -- the clone root is
    `/repos/<owner>/<repo>` there, with `/workspace/<repo>` a symlink to it and
    `/workspace` its parent.

    It also runs BEFORE the executable cases below for a practical reason: a step
    carrying an absolute `/workspace` path, executed here, would write into the
    REAL sandbox root of whatever factory stage is running this suite.
    """
    steps = _prepare_steps()
    assert len(steps) == 2
    for script in steps:
        assert _SANDBOX_ROOT not in script
        assert _CLONE_ROOT_RESOLUTION in script
    # And the overlay the dispatch submits carries the same two, so this is a
    # claim about a dispatch rather than about a renderer nobody composes.
    for script in (*_prepare_scripts(overlay=_ordinary_overlay(tmp_path=tmp_path)),):
        if _SETTINGS_RELATIVE_PATH in script:
            assert _SANDBOX_ROOT not in script


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


@pytest.mark.parametrize(
    ("layout", "clone_segments"),
    [
        # The Petri-era layout: the clone's TOP LEVEL is the sandbox root.
        ("petri", ()),
        # The pinned layout: the clone sits one directory below it.
        ("pinned", ("repo",)),
        # The layout measured inside a live hp sandbox on 2026-10-16, which is
        # neither of the two the sibling exclude module documents.
        ("measured", ("repos", "owner", "repo")),
    ],
)
def test_the_prepare_steps_land_the_settings_source_at_the_clone_root(
    tmp_path: Path,
    layout: str,
    clone_segments: tuple[str, ...],
) -> None:
    """The file the harness loads, in three layouts, from the steps themselves.

    THREE layouts because the defect is a fact about the layout rather than about
    the bytes: a fixed prefix is correct in at most one of them, and the one it
    was written for is not the one the factory runs. The clone root is the only
    answer that is right in all three, so the cases differ ONLY in where the
    clone sits under the sandbox root.

    The seeded `permissions` key is the merge assertion that matters most at this
    path, and it is why the merge is REQUIRED here rather than defensive: the
    harness writes its own permission approvals into this very file while the run
    is driving, so an overwrite would discard live session state.
    """
    sandbox_root = tmp_path / "workspace"
    repo = _git_repo(root=sandbox_root.joinpath(*clone_segments))
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / _SETTINGS_RELATIVE_PATH).write_text(
        json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8"
    )

    for script in _prepare_steps():
        _run_prepare_step(script=script, repo=repo)

    document = json.loads((repo / _SETTINGS_RELATIVE_PATH).read_text(encoding="utf-8"))
    assert document["env"]["BASH_DEFAULT_TIMEOUT_MS"] == "600000"
    assert document["env"]["BASH_MAX_TIMEOUT_MS"] == "3600000"
    assert document["permissions"] == {"allow": ["Bash"]}, layout
    # Nothing was written above the clone root, which is what a layout-assuming
    # path would do in the two cases where the clone is not the sandbox root.
    assert not (sandbox_root / ".claude").exists() or sandbox_root == repo


def test_no_checkpoint_can_stage_the_settings_source_the_steps_write(
    tmp_path: Path,
) -> None:
    """The exclusion becomes load-bearing exactly when the path moves inside.

    At the fixed `/workspace` path the paired exclude step could never write an
    entry at all -- `/workspace/.claude` is inside no worktree, so the shared
    script took its pass-over arm and exited 0, which the live sandbox's
    `info/exclude` confirmed by holding only the default template. Moving the
    write to the clone root is what makes the exclusion real, so it is measured
    here rather than assumed, and measured through git rather than by reading the
    exclude file: an entry git does not honour is not an exclusion.

    The committed `.claude/settings.json` is the positive control. It proves the
    exclusion is the NARROW one the shared renderer requires -- one file, not the
    `.claude` directory a governed repository legitimately tracks -- so a clean
    staging result is a measurement rather than a directory hidden wholesale.
    """
    repo = _git_repo(root=tmp_path / "workspace")
    _commit_file(
        repo=repo,
        name=_COMMITTED_SETTINGS_RELATIVE_PATH,
        body=json.dumps({"env": {"BASH_MAX_TIMEOUT_MS": "1200000"}}),
    )

    for script in _prepare_steps():
        _run_prepare_step(script=script, repo=repo)
    _git("add", "-A", repo=repo)

    staged = _git_stdout("diff", "--cached", "--name-only", repo=repo).split()
    assert _SETTINGS_RELATIVE_PATH not in staged
    assert (repo / _SETTINGS_RELATIVE_PATH).is_file()
    assert _COMMITTED_SETTINGS_RELATIVE_PATH in _git_stdout("ls-files", repo=repo).split()


def test_a_step_that_cannot_resolve_the_clone_root_refuses_and_says_so(
    tmp_path: Path,
) -> None:
    """An unresolvable clone root fails CLOSED, naming the projection.

    The write is the one arm here that must refuse rather than pass over. The
    sibling exclusion passes over because a path outside every worktree is one
    git was never going to stage, and the unparseable-document arm rewrites
    because a per-sandbox file that no longer parses must not kill a run at
    launch. An unresolvable clone root is neither: there is nowhere to put the
    file the harness reads, so proceeding would leave the sandbox capped at the
    committed project value with nothing but a log line to say so -- the exact
    silent failure this work-item exists to close.

    The ceiling is how the arm is reached at all, and it is a measurement rather
    than a stub: this suite's session fixture makes pytest's temp ROOT a real
    origin-reachable worktree, so every `tmp_path` is INSIDE a clone and a plain
    empty directory would resolve a toplevel. `GIT_CEILING_DIRECTORIES` stops
    git's own discovery walk, which is the same answer git gives in a sandbox
    whose clone is not where the step is standing.
    """
    outside = tmp_path / "no-clone-here"
    outside.mkdir()
    write_step = _prepare_steps()[-1]

    step = subprocess.run(
        ["/bin/sh", "-c", write_step],
        cwd=outside,
        capture_output=True,
        text=True,
        timeout=_STEP_TIMEOUT_SECONDS,
        env={**os.environ, "GIT_CEILING_DIRECTORIES": str(tmp_path)},
        check=False,
    )

    assert step.returncode != 0
    assert HARNESS_SETTINGS_MARKER in step.stderr
    assert not (outside / _SETTINGS_RELATIVE_PATH).exists()


def _git_repo(*, root: Path) -> Path:
    """A throwaway clone rooted at `root`, with one tracked file and a commit."""
    root.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch", _DEFAULT_BRANCH],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    _git("config", "user.email", "fixture@example.invalid", repo=root)
    _git("config", "user.name", "Fixture", repo=root)
    _commit_file(repo=root, name="tracked.txt", body="the repository's own content\n")
    return root


def _git(*argv: str, repo: Path) -> None:
    subprocess.run(["git", *argv], cwd=repo, capture_output=True, text=True, check=True)


def _git_stdout(*argv: str, repo: Path) -> str:
    completed = subprocess.run(
        ["git", *argv],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _commit_file(*, repo: Path, name: str, body: str) -> None:
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    _git("add", name, repo=repo)
    _git("commit", "-m", f"add {name}", repo=repo)


def _run_prepare_step(*, script: str, repo: Path) -> None:
    """Execute ONE rendered prepare step the way the engine's shell does.

    The engine runs each step with the clone as its working directory, which is
    what the committed chain's own `git fetch --unshallow` already depends on, so
    that is the one thing these cases hand the script.
    """
    step = subprocess.run(
        ["/bin/sh", "-c", script],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=_STEP_TIMEOUT_SECONDS,
        check=False,
    )

    assert step.returncode == 0, f"{script}\n{step.stdout}\n{step.stderr}"


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
