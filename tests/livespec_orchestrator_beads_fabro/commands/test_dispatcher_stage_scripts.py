"""The scripted publication stages' command bodies stay out of every agent prompt.

The Petri-era engine's `compact` fidelity renders each completed command stage
into the preamble of every later agent request as its full `Script:` text. The
`publish_draft`, `pr_refresh`, `pr` and `pr_refresh_head` scripts are about
58,000 characters that no agent turn reads, so the Dispatcher splits them in the
per-dispatch copy of the graph: the node's script becomes a short invocation of a
helper file, and the helper's bytes ride the `env` of one prepare step.

The tests bind both halves of the Definition of Done. The prompt half: no
rendered node script carries a body. The behaviour half: the helper is the
committed body with only its template inputs rebound, and a helper run through
its invocation ends exactly as the original script did on the same inputs.

The template opener is ASSEMBLED rather than written literally, the fleet
convention of livespec-dev-tooling-9yb4.
"""

from __future__ import annotations

import re
import shlex
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    materialize_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stage_scripts import (
    STAGE_SCRIPT_NODES,
    StageScripts,
    externalize_stage_scripts,
    materialize_stage_helpers,
    stage_script_filename,
    stage_script_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import default_node_timeouts

from tests.prepare_step_support import env_of, runnable_script, steps_in

_PLUGIN_ROOT = Path(dispatcher.__file__).resolve().parents[3]
_WORKFLOW_DIR = _PLUGIN_ROOT / ".fabro" / "workflows" / "implement-work-item"
_COMMITTED_GRAPH = _WORKFLOW_DIR / "workflow.fabro"
_COMMITTED_WORKFLOW = _WORKFLOW_DIR / "workflow.toml"

_OPEN = "{" + "{"
_CLOSE = "}" + "}"
_ROOT_VAR = "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT"
_PATH = "/usr/local/bin:/usr/bin:/bin"
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"
_INVOCATION_CEILING = 600
_MOVED_AT_LEAST = 50_000


def _token(*, name: str) -> str:
    return f"{_OPEN} inputs.{name} {_CLOSE}"


def _node_script_line(*, text: str, node: str) -> str:
    """The raw `script="..."` line of one node, as the graph file carries it."""
    block = re.search(rf"(?ms)^    {node} \[\n(.*?)^    \]$", text)
    assert block is not None, node
    lines = [line for line in block.group(1).splitlines() if line.startswith('        script="')]
    assert len(lines) == 1, node
    return lines[0]


def _decode(*, line: str) -> str:
    """A script line's value, decoded the way the graph parser decodes it."""
    raw = line.removeprefix('        script="').removesuffix('"')
    return re.sub(r'\\([\\"])', r"\1", raw)


def _committed_text() -> str:
    return _COMMITTED_GRAPH.read_text(encoding="utf-8")


def _split() -> StageScripts:
    split = externalize_stage_scripts(graph_text=_committed_text())
    assert isinstance(split, StageScripts), split
    return split


def _escaped(*, script: str) -> str:
    return script.replace("\\", "\\\\").replace('"', '\\"')


def _graph(*, nodes: dict[str, str]) -> str:
    """A minimal graph whose named nodes each carry the given decoded script."""
    blocks = "".join(
        "".join(
            [
                f'    {node} [\n        label="x"\n        shape=parallelogram\n',
                f'        script="{_escaped(script=script)}"\n',
                "    ]\n\n",
            ]
        )
        for node, script in nodes.items()
    )
    return f'digraph G {{\n    graph [\n        stall_timeout="7200s"\n    ]\n\n{blocks}}}\n'


def test_every_stage_script_becomes_a_short_invocation_of_its_helper() -> None:
    split = _split()
    for node in STAGE_SCRIPT_NODES:
        decoded = _decode(line=_node_script_line(text=split.text, node=node))
        assert len(decoded) < _INVOCATION_CEILING, node
        assert stage_script_filename(node=node) in decoded, node
        assert "$HOME/.claude/plugins" in decoded, node


def test_the_split_moves_the_bodies_out_of_the_graph() -> None:
    split = _split()
    committed = _committed_text()
    assert len(committed) - len(split.text) > _MOVED_AT_LEAST
    assert set(split.helpers) == set(STAGE_SCRIPT_NODES)
    for node in STAGE_SCRIPT_NODES:
        body = _decode(line=_node_script_line(text=committed, node=node))
        assert body[:200] not in split.text, node
        assert body[-200:] not in split.text, node


def test_only_the_four_scripts_changed() -> None:
    committed = _committed_text().splitlines()
    rendered = _split().text.splitlines()
    assert len(committed) == len(rendered)
    changed = [
        index
        for index, (before, after) in enumerate(zip(committed, rendered, strict=True))
        if before != after
    ]
    assert len(changed) == len(STAGE_SCRIPT_NODES)
    assert all(committed[index].startswith('        script="') for index in changed)


def test_a_helper_is_the_committed_body_with_only_its_inputs_rebound() -> None:
    split = _split()
    for node in STAGE_SCRIPT_NODES:
        body = _decode(line=_node_script_line(text=_committed_text(), node=node))
        helper = split.helpers[node]
        assert _OPEN not in helper, node
        assert "{" + "%" not in helper, node
        rebuilt = re.sub(
            re.escape(_OPEN)
            + r" inputs\.(default_branch|merge_hold|merge_mode) "
            + re.escape(_CLOSE),
            lambda match: "${LIVESPEC_STAGE_INPUT_" + match.group(1).upper() + "}",
            body.replace(
                f"set -- {_token(name='sandbox_check_suite')}",
                'eval "set -- $livespec_suite_words"',
            ),
        )
        assert helper.endswith(rebuilt + "\n"), node


def test_every_helper_parses_as_shell(tmp_path: Path) -> None:
    for node, helper in _split().helpers.items():
        path = tmp_path / stage_script_filename(node=node)
        _ = path.write_text(helper, encoding="utf-8")
        parsed = subprocess.run(
            ["sh", "-n", str(path)], capture_output=True, text=True, check=False
        )
        assert parsed.returncode == 0, (node, parsed.stderr)


def test_each_invocation_still_carries_the_inputs_its_body_used() -> None:
    split = _split()
    expected = {
        "publish_draft": {"default_branch", "sandbox_check_suite"},
        "pr_refresh": {"default_branch", "sandbox_check_suite"},
        "pr": {"default_branch", "merge_hold", "merge_mode"},
        "pr_refresh_head": {"default_branch"},
    }
    for node, names in expected.items():
        decoded = _decode(line=_node_script_line(text=split.text, node=node))
        assert set(re.findall(r"inputs\.(\w+)", decoded)) == names, node


def test_a_graph_without_the_stage_nodes_is_left_alone() -> None:
    graph = _graph(nodes={"janitor": "true"})
    split = externalize_stage_scripts(graph_text=graph)
    assert isinstance(split, StageScripts)
    assert split.text == graph
    assert split.helpers == {}


def test_an_input_with_no_seam_into_a_helper_is_refused() -> None:
    graph = _graph(nodes={"pr": f"echo {_token(name='something_else')}"})
    refusal = externalize_stage_scripts(graph_text=graph)
    assert isinstance(refusal, str)
    assert "pr" in refusal
    assert "something_else" in refusal


def test_the_suite_token_outside_a_set_assignment_is_refused() -> None:
    graph = _graph(nodes={"pr_refresh": f"echo {_token(name='sandbox_check_suite')}"})
    refusal = externalize_stage_scripts(graph_text=graph)
    assert isinstance(refusal, str)
    assert "sandbox_check_suite" in refusal


_SUITE_SCRIPT = (
    f"gate() {{ set -- {_token(name='sandbox_check_suite')}; "
    'if test "$#" -eq 1; then eval "set -- $1"; fi; '
    'for word in "$@"; do printf "[%s]\\n" "$word"; done; }; gate; '
    f'echo "branch=\'{_token(name="default_branch")}\'"'
)


def _run(*, argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, capture_output=True, text=True, check=False, env=env, cwd=env["PWD"]
    )


@pytest.mark.parametrize(
    "suite",
    [
        "mise exec -- just check",
        "sh -c 'echo it'\"'\"'s fine'",
        "uv run pytest -k 'a b'",
        "",
    ],
)
@pytest.mark.parametrize("quoted_as_one_word", [True, False])
def test_the_check_suite_reaches_a_helper_as_the_engine_would_render_it(
    *, suite: str, quoted_as_one_word: bool, tmp_path: Path
) -> None:
    split = externalize_stage_scripts(graph_text=_graph(nodes={"pr_refresh": _SUITE_SCRIPT}))
    assert isinstance(split, StageScripts)
    helper = tmp_path / stage_script_filename(node="pr_refresh")
    _ = helper.write_text(split.helpers["pr_refresh"], encoding="utf-8")
    suite_word = shlex.quote(suite) if quoted_as_one_word else suite
    env = {"PATH": _PATH, "HOME": str(tmp_path), _ROOT_VAR: str(tmp_path), "PWD": str(tmp_path)}
    original = _SUITE_SCRIPT.replace(_token(name="sandbox_check_suite"), suite_word).replace(
        _token(name="default_branch"), "trunk"
    )
    invocation = _decode(line=_node_script_line(text=split.text, node="pr_refresh"))
    rendered = invocation.replace(_token(name="sandbox_check_suite"), suite_word).replace(
        _token(name="default_branch"), "trunk"
    )
    before = _run(argv=["sh", "-c", original], env=env)
    after = _run(argv=["sh", "-c", rendered], env=env)
    assert after.returncode == before.returncode
    assert after.stdout == before.stdout
    assert after.stderr == before.stderr
    assert "branch='trunk'" in after.stdout


def _fake_forge(*, directory: Path, program_exit: int) -> dict[str, str]:
    """A sandbox for `pr_refresh_head`: a fake `gh`, a recording decision program, a state dir."""
    bin_dir = directory / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    _ = gh.write_text("#!/bin/sh\necho 7\n", encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    plugins = directory / "plugins"
    plugins.mkdir()
    program = [
        "import sys",
        "from pathlib import Path",
        f"Path({str(directory / 'argv.txt')!r}).write_text(' '.join(sys.argv[1:]))",
        f"sys.exit({program_exit})",
    ]
    _ = (plugins / "livespec-carry-forward-decision.py").write_text(
        "\n".join(program) + "\n", encoding="utf-8"
    )
    repo = directory / "repo"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "-q", str(repo)], check=True)
    state = repo / ".git" / "livespec-publication"
    state.mkdir()
    for name, value in (
        ("changed", "1"),
        ("previous-head", "aaa"),
        ("previous-base", "bbb"),
        ("new-base", "ccc"),
        ("new-head", "ddd"),
    ):
        _ = (state / f"livespec-pr-refresh-{name}").write_text(value, encoding="utf-8")
    return {
        "PATH": f"{bin_dir}:{_PATH}",
        "HOME": str(directory),
        _ROOT_VAR: str(plugins),
        "LIVESPEC_PUBLISH_BRANCH": "feat/x",
        "PWD": str(repo),
    }


@pytest.mark.parametrize("program_exit", [0, 1])
def test_pr_refresh_head_ends_the_same_way_through_its_helper(
    *, program_exit: int, tmp_path: Path
) -> None:
    env = _fake_forge(directory=tmp_path, program_exit=program_exit)
    split = _split()
    committed = _decode(line=_node_script_line(text=_committed_text(), node="pr_refresh_head"))
    helper = Path(env[_ROOT_VAR]) / stage_script_filename(node="pr_refresh_head")
    _ = helper.write_text(split.helpers["pr_refresh_head"], encoding="utf-8")
    invocation = _decode(line=_node_script_line(text=split.text, node="pr_refresh_head"))
    argv_file = tmp_path / "argv.txt"
    seen: list[tuple[int, str, str]] = []
    for script in (
        committed.replace(_token(name="default_branch"), "trunk"),
        invocation.replace(_token(name="default_branch"), "trunk"),
    ):
        _ = argv_file.unlink(missing_ok=True)
        done = _run(argv=["sh", "-c", script], env=env)
        seen.append((done.returncode, done.stderr, argv_file.read_text(encoding="utf-8")))
    assert seen[0] == seen[1]
    assert seen[1][0] == program_exit
    assert "--default-branch trunk " in seen[1][2]


def _payload(*, payload_dir: Path) -> WorkflowPayload:
    declared = workflow_declared_inputs(
        committed_text=_COMMITTED_WORKFLOW.read_text(encoding="utf-8")
    )
    payload = materialize_workflow_payload(
        committed=_COMMITTED_WORKFLOW,
        payload_dir=payload_dir,
        timeouts=default_node_timeouts(),
        adapters={name: value for name, value in declared.items() if name.endswith("_adapter")},
    )
    assert isinstance(payload, WorkflowPayload), payload
    return payload


def test_the_dispatched_payload_graph_carries_no_stage_script_body(tmp_path: Path) -> None:
    payload = _payload(payload_dir=tmp_path / "payload")
    dispatched = payload.graph.read_text(encoding="utf-8")
    committed = _committed_text()
    for node in STAGE_SCRIPT_NODES:
        body = _decode(line=_node_script_line(text=committed, node=node))
        assert body[:200] not in dispatched, node
        decoded = _decode(line=_node_script_line(text=dispatched, node=node))
        assert len(decoded) < _INVOCATION_CEILING, node
    assert len(committed) - len(dispatched) > _MOVED_AT_LEAST


def _overlay(*, graph: Path | None, artifact: Path | None) -> str | None:
    return render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW.read_text(encoding="utf-8"),
        workflow_dir=_WORKFLOW_DIR,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        graph_override=graph,
        graph_artifact=artifact,
    )


def test_the_overlay_extracts_helpers_without_serializing_them_into_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _payload(payload_dir=tmp_path / "payload")
    rendered = _overlay(graph=payload.graph, artifact=payload.graph)
    assert rendered is not None
    split = _split()
    steps = [
        step for step in steps_in(block=rendered) if "materialize_stage_helpers" in step.script
    ]
    assert len(steps) == 1
    step = steps[0]
    assert len(step.script) < _INVOCATION_CEILING
    assert step.env == {}
    assert all(helper not in rendered for helper in split.helpers.values())
    assert len(rendered.encode()) <= 471_859
    materialized_root = tmp_path / "direct-helpers"
    monkeypatch.setenv(_ROOT_VAR, str(materialized_root))
    materialize_stage_helpers(committed_graph=_COMMITTED_GRAPH, rendered_graph=payload.graph)
    for node, helper in split.helpers.items():
        assert (materialized_root / stage_script_filename(node=node)).read_text(
            encoding="utf-8"
        ) == helper
    home = tmp_path / "home"
    home.mkdir()
    uv = shutil.which("uv")
    assert uv is not None
    base = {
        "PATH": f"{Path(uv).parent}:{_PATH}",
        "PYTHONPATH": str(_PLUGIN_ROOT / "scripts"),
        "HOME": str(home),
        "PWD": str(home),
    }
    done = _run(argv=["sh", "-c", runnable_script(step=step)], env=env_of(step=step, base=base))
    assert done.returncode == 0, done.stderr
    for node, helper in split.helpers.items():
        written = home / ".claude" / "plugins" / stage_script_filename(node=node)
        assert written.read_text(encoding="utf-8") == helper


def test_the_overlay_writes_no_helper_when_the_graph_was_not_split() -> None:
    for graph, artifact in ((None, None), (_COMMITTED_GRAPH, _COMMITTED_GRAPH)):
        rendered = _overlay(graph=graph, artifact=artifact)
        assert rendered is not None
        scripts = "".join(step.script for step in steps_in(block=rendered))
        assert not any(stage_script_filename(node=node) in scripts for node in STAGE_SCRIPT_NODES)


def test_no_prepare_step_for_a_graph_that_was_not_split() -> None:
    block = stage_script_prepare_steps_block(
        committed_graph=_COMMITTED_GRAPH, rendered_graph=_COMMITTED_GRAPH
    )
    assert block == ""
    assert (
        stage_script_prepare_steps_block(committed_graph=_COMMITTED_GRAPH, rendered_graph=None)
        == ""
    )


def test_an_unreadable_graph_refuses_the_prepare_step(tmp_path: Path) -> None:
    payload = _payload(payload_dir=tmp_path / "payload")
    missing = tmp_path / "missing.fabro"
    assert (
        stage_script_prepare_steps_block(committed_graph=_COMMITTED_GRAPH, rendered_graph=missing)
        is None
    )
    assert (
        stage_script_prepare_steps_block(committed_graph=missing, rendered_graph=payload.graph)
        is None
    )


def test_a_committed_graph_the_split_refuses_refuses_the_prepare_step(tmp_path: Path) -> None:
    payload = _payload(payload_dir=tmp_path / "payload")
    bad = tmp_path / "bad.fabro"
    _ = bad.write_text(
        _graph(nodes={"pr": f"echo {_token(name='something_else')}"}), encoding="utf-8"
    )
    assert (
        stage_script_prepare_steps_block(committed_graph=bad, rendered_graph=payload.graph) is None
    )


def test_materializing_helpers_rejects_an_unseamed_body_and_skips_uninvoked_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "bad.fabro"
    _ = bad.write_text(
        _graph(nodes={"pr": f"echo {_token(name='something_else')}"}), encoding="utf-8"
    )
    monkeypatch.setenv(_ROOT_VAR, str(tmp_path / "helpers"))
    with pytest.raises(TypeError, match="something_else"):
        materialize_stage_helpers(committed_graph=bad, rendered_graph=bad)

    committed = tmp_path / "committed.fabro"
    _ = committed.write_text(
        _graph(nodes={"pr": f"echo {_token(name='default_branch')}"}), encoding="utf-8"
    )
    split = externalize_stage_scripts(graph_text=committed.read_text(encoding="utf-8"))
    assert isinstance(split, StageScripts)
    rendered = tmp_path / "rendered.fabro"
    _ = rendered.write_text(split.text, encoding="utf-8")
    materialize_stage_helpers(committed_graph=committed, rendered_graph=rendered)
    assert (tmp_path / "helpers" / stage_script_filename(node="pr")).is_file()
    _ = rendered.write_text("digraph G {}\n", encoding="utf-8")
    materialize_stage_helpers(committed_graph=committed, rendered_graph=rendered)
