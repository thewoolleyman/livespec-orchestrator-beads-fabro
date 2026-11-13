"""A publish_draft push refused for an oversize file or by the pre-push hook is repaired through fix.

Binds work-item ``bd-ib-7owmkq`` to ``SPECIFICATION/scenarios.md`` Scenario 329 and
the Scenario 224 GH001 case, governed by ``contracts.md`` "Self-contained plugin
dispatch" -> "Publish repair". The measured incident (openbrain run
01M6WF7GHVJX4NGBK1R4XHY8KW) ended at needs-human with
``LIVESPEC_REFRESH_REPAIR_ABSENT`` because GitHub refused the push with GH001 for
two oversize files and the stage recorded no brief for ``fix`` to read.

EVERY CASE EXECUTES THE SHIPPED SCRIPT BYTES of ``publish_draft`` and the
``refresh_repair`` classifier, extracted through the canonical DOT parser, against
a real throwaway origin and clone. The origin's ``pre-receive`` hook stands in for
GitHub's push-time file-size and branch-protection refusals; only the engine's own
template tokens are substituted.
"""

from __future__ import annotations

import shlex
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_DEFAULT_BRANCH = "master"
_BRANCH = "feat/bd-ib-7owmkq"
_BRIEF = "livespec-refresh-repair-brief"
_COUNT = "livespec-refresh-repair-count"
_EXHAUSTED = "livespec-refresh-repair-exhausted"
_ABSENT = "LIVESPEC_REFRESH_REPAIR_ABSENT"
_OVERSIZE = (".pnpm-store/a.bin", ".pnpm-store/b.bin")
_GH001_HOOK = "\n".join(
    (
        "#!/bin/sh",
        "while read old new ref; do",
        "  for path in $(git ls-tree -r --name-only \"$new\" | grep '^[.]pnpm-store/'); do",
        '    case "$path" in',
        '      *a.bin) size="119.00 MB" ;;',
        '      *) size="124.00 MB" ;;',
        "    esac",
        '    echo "error: File $path is $size; this exceeds GitHub\'s file size limit of 100.00 MB" >&2',
        "    found=yes",
        "  done",
        "done",
        'if test "${found:-}" = yes; then',
        '  echo "error: GH001: Large files detected." >&2',
        "  exit 1",
        "fi",
        "",
    )
)
_PROTECTED_HOOK = "\n".join(
    (
        "#!/bin/sh",
        "cat >/dev/null",
        'echo "error: GH006: Protected branch update failed for refs/heads/x." >&2',
        "exit 1",
        "",
    )
)
_HOOK_REFUSAL = "\n".join(
    (
        "#!/bin/sh",
        "n=0",
        "while test $n -lt 120; do n=$((n + 1)); printf 'hook-line-%03d\\n' $n >&2; done",
        "printf '%s\\n' 'Failed targets (2):' >&2",
        "printf '%s\\n' '  - lint' >&2",
        "printf '%s\\n' '  - format' >&2",
        "exit 1",
        "",
    )
)


def _git(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        },
    )


def _install(*, path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _world(*, root: Path, oversize: bool) -> Path:
    """A bare origin and a clone on a run branch, optionally carrying two oversize files."""
    origin = root / "origin.git"
    origin.mkdir()
    _ = _git("init", "--bare", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=origin)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=seed)
    _ = (seed / "shared.txt").write_text("base\n", encoding="utf-8")
    _ = _git("add", "shared.txt", cwd=seed)
    _ = _git("commit", "--quiet", "-m", "chore: seed", cwd=seed)
    _ = _git("push", "--quiet", str(origin), f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=seed)
    clone = root / "clone"
    _ = _git("clone", "--quiet", str(origin), str(clone), cwd=root)
    _ = _git("switch", "--quiet", "-c", "fabro/run/test", cwd=clone)
    _ = (clone / "owned.txt").write_text("run\n", encoding="utf-8")
    _ = _git("add", "owned.txt", cwd=clone)
    if oversize:
        for name in _OVERSIZE:
            _install(path=clone / name, body="stand-in for a very large file\n")
            _ = _git("add", name, cwd=clone)
    _ = _git("commit", "--quiet", "-m", "feat: run work", cwd=clone)
    return clone


def _node_script(*, node: str) -> str:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes[node]["script"]
    return (
        script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)
        .replace("{{ inputs.sandbox_check_suite }}", "true")
        .replace("{{ inputs.conformance_hook_install }}", "")
    )


def _arms(*, source: str) -> list[tuple[str, str | None]]:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return [
        (edge.destination, edge.attributes.get("condition"))
        for edge in graph.edges
        if edge.source == source
    ]


def _refusing_git_bin(*, root: Path, refusal: str) -> Path:
    real_git = shutil.which("git")
    assert real_git is not None
    bin_dir = root / "refusing-bin"
    _install(
        path=bin_dir / "git",
        body="\n".join(
            (
                "#!/bin/sh",
                'if test "$1" = push; then',
                f"    printf '%s\\n' {shlex.quote(refusal)} >&2",
                "    exit 1",
                "fi",
                f'exec {shlex.quote(real_git)} "$@"',
                "",
            )
        ),
    )
    return bin_dir


def _env(*, root: Path, refusal: str | None) -> dict[str, str]:
    plugins = root / "plugins"
    plugins.mkdir(exist_ok=True)
    _ = (plugins / RECORD_FILE_MERGE_PROGRAM_FILENAME).write_text(
        record_file_merge_program_source(), encoding="utf-8"
    )
    _ = (plugins / RECORD_FILE_PROGRAM_FILENAME).write_text(
        record_file_program_source(), encoding="utf-8"
    )
    _install(
        path=plugins / PUBLICATION_PUSH_PROGRAM_FILENAME, body=publication_push_program_source()
    )
    _install(path=root / "bin" / "gh", body="#!/bin/sh\necho null\n")
    prefix = ""
    if refusal is not None:
        prefix = f"{_refusing_git_bin(root=root, refusal=refusal)}:"
    return {
        "PATH": f"{prefix}{root / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(root / "home"),
        "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
        "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(root / "no-gh-refresh"),
        "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins),
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }


def _run(
    *, node: str, root: Path, clone: Path, refusal: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", _node_script(node=node)],
        cwd=clone,
        check=False,
        capture_output=True,
        text=True,
        env=_env(root=root, refusal=refusal),
    )


def _state(*, clone: Path, name: str) -> Path:
    return clone / ".git" / PUBLICATION_STATE_GIT_PATH / name


def _reason(*, clone: Path) -> str:
    path = clone / ".git" / "livespec-needs-human-reason"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _head(*, clone: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=clone).stdout.strip()


def _remote_head(*, clone: Path) -> str:
    out = _git("ls-remote", "--heads", "origin", f"refs/heads/{_BRANCH}", cwd=clone).stdout
    return out.split()[0] if out.strip() else ""


def test_a_gh001_rejection_reaches_fix_with_a_brief_naming_each_oversize_path(
    tmp_path: Path,
) -> None:
    """Scenario 329: the brief names publish_draft, the refused head, each path and its size."""
    clone = _world(root=tmp_path, oversize=True)
    _install(path=tmp_path / "origin.git" / "hooks" / "pre-receive", body=_GH001_HOOK)
    refused = _head(clone=clone)

    result = _run(node="publish_draft", root=tmp_path, clone=clone)
    classifier = _run(node="refresh_repair", root=tmp_path, clone=clone)

    assert result.returncode != 0, result.stdout
    brief = _state(clone=clone, name=_BRIEF).read_text(encoding="utf-8")
    assert "stage: publish_draft" in brief
    assert f"refused-head: {refused}" in brief
    assert ".pnpm-store/a.bin (119.00 MB)" in brief
    assert ".pnpm-store/b.bin (124.00 MB)" in brief
    assert _state(clone=clone, name=_COUNT).read_text(encoding="utf-8") == "1\n"
    assert _head(clone=clone) == refused
    assert _remote_head(clone=clone) == ""
    assert classifier.returncode == 0, classifier.stderr
    assert "LIVESPEC_REFRESH_REPAIR_PENDING" in classifier.stderr
    assert _ABSENT not in classifier.stderr
    assert ("fix", "outcome=succeeded") in _arms(source="refresh_repair")


def test_a_gh001_failure_output_names_the_rejection_each_path_and_its_size(
    tmp_path: Path,
) -> None:
    """Scenario 224: the failure output names GH001, each oversize path and its size."""
    clone = _world(root=tmp_path, oversize=True)
    _install(path=tmp_path / "origin.git" / "hooks" / "pre-receive", body=_GH001_HOOK)

    result = _run(node="publish_draft", root=tmp_path, clone=clone)

    assert "GH001" in result.stderr
    assert ".pnpm-store/a.bin (119.00 MB)" in result.stderr
    assert ".pnpm-store/b.bin (124.00 MB)" in result.stderr


def test_the_publish_after_a_repair_that_removed_the_path_publishes_the_repaired_head(
    tmp_path: Path,
) -> None:
    """Scenario 329: once fix has removed the path the re-entered publish_draft succeeds."""
    clone = _world(root=tmp_path, oversize=True)
    _install(path=tmp_path / "origin.git" / "hooks" / "pre-receive", body=_GH001_HOOK)
    first = _run(node="publish_draft", root=tmp_path, clone=clone)
    _ = _git("rm", "-rf", "--quiet", ".pnpm-store", cwd=clone)
    _ = _git("commit", "--quiet", "--amend", "--no-edit", cwd=clone)

    second = _run(node="publish_draft", root=tmp_path, clone=clone)

    assert first.returncode != 0
    assert second.returncode == 0, second.stderr
    assert _remote_head(clone=clone) == _head(clone=clone)
    assert not _state(clone=clone, name=_BRIEF).exists()
    assert _state(clone=clone, name=_COUNT).read_text(encoding="utf-8") == "1\n"
    assert ("janitor_admission", None) in _arms(source="fix_commit_settle")
    assert ("janitor", None) in _arms(source="janitor_admission")
    assert ("publish_draft", "outcome=succeeded") in _arms(source="janitor")
    assert ("proof_capture", None) in _arms(source="publish_merged_reconcile_route")


def test_a_pre_push_hook_refusal_reaches_fix_with_its_failed_targets_and_output_tail(
    tmp_path: Path,
) -> None:
    """Scenario 329: the brief names each failed target and the last 80 lines of hook output."""
    clone = _world(root=tmp_path, oversize=False)
    _install(path=clone / ".git" / "hooks" / "pre-push", body=_HOOK_REFUSAL)
    refused = _head(clone=clone)

    result = _run(node="publish_draft", root=tmp_path, clone=clone)
    classifier = _run(node="refresh_repair", root=tmp_path, clone=clone)

    assert result.returncode != 0, result.stdout
    brief = _state(clone=clone, name=_BRIEF).read_text(encoding="utf-8")
    assert "stage: publish_draft" in brief
    assert f"refused-head: {refused}" in brief
    assert "failed-gate-targets: lint, format" in brief
    assert "hook-line-120" in brief
    assert "hook-line-010" not in brief
    assert classifier.returncode == 0, classifier.stderr
    assert _ABSENT not in classifier.stderr


@pytest.mark.parametrize(
    ("kind", "needle", "refusal"),
    [
        ("protected-branch", "protected", None),
        ("non-fast-forward", "non-fast-forward", "! [rejected] HEAD -> x (non-fast-forward)"),
        ("origin-unreachable", "could not be reached", "fatal: Could not resolve host: o.invalid"),
        (
            "authentication",
            "authentication",
            "fatal: Authentication failed for 'https://o.invalid'",
        ),
    ],
)
def test_every_other_refusal_stays_fail_closed_naming_its_own_cause(
    tmp_path: Path, kind: str, needle: str, refusal: str | None
) -> None:
    """Scenario 329: no brief, no fix, and the needs-human reason names the refusal."""
    clone = _world(root=tmp_path, oversize=False)
    if refusal is None:
        _install(path=tmp_path / "origin.git" / "hooks" / "pre-receive", body=_PROTECTED_HOOK)

    result = _run(node="publish_draft", root=tmp_path, clone=clone, refusal=refusal)
    classifier = _run(node="refresh_repair", root=tmp_path, clone=clone)

    assert result.returncode != 0, result.stdout
    assert needle in result.stderr
    assert not _state(clone=clone, name=_BRIEF).exists()
    assert not _state(clone=clone, name=_COUNT).exists()
    assert classifier.returncode != 0
    assert ("needs_human", None) in _arms(source="refresh_repair")
    reason = _reason(clone=clone)
    assert reason.startswith(f"publish-push-{kind}:"), reason
    assert needle in reason
    assert _ABSENT not in reason


def test_a_publish_repair_counts_toward_the_budget_and_names_the_refused_head(
    tmp_path: Path,
) -> None:
    """Scenario 329: a third repair fails closed as refresh-repair-exhausted at the refused head."""
    clone = _world(root=tmp_path, oversize=True)
    _install(path=tmp_path / "origin.git" / "hooks" / "pre-receive", body=_GH001_HOOK)
    _state(clone=clone, name=_COUNT).parent.mkdir(parents=True)
    _ = _state(clone=clone, name=_COUNT).write_text("2\n", encoding="utf-8")
    refused = _head(clone=clone)

    result = _run(node="publish_draft", root=tmp_path, clone=clone)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_REFRESH_REPAIR_EXHAUSTED" in result.stderr
    first_line = _reason(clone=clone).splitlines()[0]
    assert first_line.startswith("refresh-repair-exhausted:")
    assert refused in first_line
    assert not _state(clone=clone, name=_BRIEF).exists()
    assert _state(clone=clone, name=_EXHAUSTED).is_file()
    assert _state(clone=clone, name=_COUNT).read_text(encoding="utf-8") == "2\n"
    assert _head(clone=clone) == refused
