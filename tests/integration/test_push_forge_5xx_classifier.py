"""A forge 5xx is recognized by its status form, never by a bare digit run.

The needs_human preservation push and the pr_refresh leased push retry a push
whose output reports a forge server error (work-item bd-ib-3d2c5y). A push
output also carries paths, object ids and byte counts, so a 5xx digit run inside
one of those must not read as a server error: a hook refusal named in a
directory like `bs531c9z` was pushed again and recorded extra hook runs.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

_IMPLEMENT = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_GROOM = Path(".fabro/workflows/groom-work-item/workflow.fabro")
_CLASSIFIER = re.compile(r"grep -qiE '(?P<pattern>[^']*5\[0-9\]\[0-9\][^']*)'")
_SCRIPT = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')
_PUBLISH_BRANCH = "feat/bd-ib-3d2c5y"
_RUN_ID = "01FORGEFIVEXX"
_WORKFLOW_PATH = ".github/workflows/run-owned.yml"
_DIGIT_RUN_DIRECTORY = "covns-full-tree-bs531c9z"

_NOT_A_SERVER_ERROR = (
    "".join(
        [
            f"To /tmp/{_DIGIT_RUN_DIRECTORY}/tmp/pytest/popen-gw2/origin.git\n",
            " ! [remote rejected] HEAD -> needs-human/01RUN (pre-receive hook declined)\n",
            f"error: failed to push some refs to '/tmp/{_DIGIT_RUN_DIRECTORY}/origin.git'\n",
        ]
    ),
    "".join(
        [
            "remote: refusing to allow a GitHub App to create or update workflow ",
            ".github/workflows/ab512cd.yml without workflows permission\n",
        ]
    ),
    "   ab512cd..9f3e501  HEAD -> feat/bd-ib-3d2c5y\n",
    "Writing objects: 100% (5/5), 512 bytes | 512.00 KiB/s, done.\n",
)
_SERVER_ERROR = (
    "".join(
        [
            "fatal: unable to access 'https://github.com/o/r.git/': ",
            "The requested URL returned error: 503\n",
        ]
    ),
    "error: RPC failed; HTTP 500 curl 22\n",
    "remote: HTTP/1.1 502\n",
)
_REFUSING_HOOK = "".join(
    [
        "#!/bin/sh\n",
        "printf x >> {pushes}\n",
        "while read -r old_revision new_revision ref; do\n",
        '    if test "$ref" = refs/heads/master; then continue; fi\n',
        '    workflow_files=$(git diff --name-only refs/heads/master "$new_revision"',
        " -- .github/workflows)\n",
        '    if test -n "$workflow_files"; then\n',
        '        echo "refusing to allow a GitHub App to create or update workflow',
        ' $workflow_files without workflows permission" >&2\n',
        "        exit 1\n",
        "    fi\n",
        "done\n",
        "exit 0\n",
    ]
)


def _git(*, cwd: Path, argv: tuple[str, ...]) -> None:
    _ = subprocess.run(["git", *argv], cwd=str(cwd), check=True, text=True, capture_output=True)


def _matches(*, pattern: str, text: str) -> bool:
    found = subprocess.run(
        ["grep", "-qiE", pattern], input=text, text=True, capture_output=True, check=False
    )
    return found.returncode == 0


def _classifiers(*, workflow: Path) -> list[str]:
    return [match.group("pattern") for match in _CLASSIFIER.finditer(workflow.read_text())]


def test_every_forge_5xx_classifier_ignores_digit_runs_and_keeps_status_forms() -> None:
    """Each classifier in both workflows reads only a status form as a 5xx."""
    implement = _classifiers(workflow=_IMPLEMENT)
    groom = _classifiers(workflow=_GROOM)
    false_server_errors = [
        (pattern, text)
        for pattern in (*implement, *groom)
        for text in _NOT_A_SERVER_ERROR
        if _matches(pattern=pattern, text=text)
    ]
    missed_server_errors = [
        (pattern, text)
        for pattern in (*implement, *groom)
        for text in _SERVER_ERROR
        if not _matches(pattern=pattern, text=text)
    ]
    facts = (
        len(implement) == 3,
        len(groom) == 2,
        false_server_errors == [],
        missed_server_errors == [],
    )
    assert all(facts), (facts, false_server_errors, missed_server_errors)


def _sandbox(*, root: Path) -> Path:
    origin = root / "origin.git"
    _git(cwd=root, argv=("init", "--bare", "-b", "master", str(origin)))
    work = root / "work"
    work.mkdir()
    for argv in (
        ("init", "-b", "master"),
        ("config", "user.name", "forge-5xx-test"),
        ("config", "user.email", "forge-5xx-test@example.invalid"),
    ):
        _git(cwd=work, argv=argv)
    _ = (work / "base.txt").write_text("base\n", encoding="utf-8")
    for argv in (
        ("add", "base.txt"),
        ("commit", "-m", "base"),
        ("remote", "add", "origin", str(origin)),
        ("push", "-u", "origin", "master"),
        ("switch", "-c", "fabro/run/forge-5xx"),
    ):
        _git(cwd=work, argv=argv)
    target = work / _WORKFLOW_PATH
    target.parent.mkdir(parents=True)
    _ = target.write_text("name: run-owned\n", encoding="utf-8")
    _git(cwd=work, argv=("add", _WORKFLOW_PATH))
    _git(cwd=work, argv=("commit", "-m", "run changes workflow"))
    hook = origin / "hooks" / "pre-receive"
    _ = hook.write_text(_REFUSING_HOOK.replace("{pushes}", str(root / "pushes")), encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    return work


def _env(*, root: Path) -> dict[str, str]:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    _ = gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            "LIVESPEC_GIT_AUTHOR_NAME": "Forge 5xx Test",
            "LIVESPEC_GIT_AUTHOR_EMAIL": "forge-5xx-test@example.invalid",
            "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
        }
    )
    return env


def _needs_human_script() -> str:
    text = _IMPLEMENT.read_text(encoding="utf-8")
    block = re.search(r"^\s*needs_human\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    assert block is not None
    attr = _SCRIPT.search(block.group("body"))
    assert attr is not None
    return re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", attr.group("value")).replace(
        "{{ inputs.default_branch }}", "master"
    )


def test_a_hook_refusal_under_a_digit_run_directory_is_pushed_once_before_its_reset(
    tmp_path: Path,
) -> None:
    """A directory name with a 5xx digit run does not repeat a refused preservation push."""
    root = tmp_path / _DIGIT_RUN_DIRECTORY
    root.mkdir()
    work = _sandbox(root=root)

    terminal = subprocess.run(
        ["sh", "-c", _needs_human_script()],
        cwd=str(work),
        env=_env(root=root),
        text=True,
        capture_output=True,
        input=f"{_RUN_ID}\n",
        check=False,
    )

    pushes = (root / "pushes").read_text(encoding="utf-8")
    facts = (
        pushes == "xx",
        f"LIVESPEC_NEEDS_HUMAN_PRESERVED: refs/heads/needs-human/{_RUN_ID}" in terminal.stderr,
        "LIVESPEC_NEEDS_HUMAN_WORKFLOWS_RESET" in terminal.stderr,
    )
    assert all(facts), (facts, pushes, terminal.stderr)
