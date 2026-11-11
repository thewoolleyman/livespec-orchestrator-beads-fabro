"""The sandbox materializer: every helper composed, verified against the manifest, then written.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", paragraph
"Helper programs are fetched in the sandbox from the dispatching build's own
commit", and Scenario 336's "The setup step writes every helper program from the
pinned commit and verifies its digest" and "A helper the setup step cannot verify
fails the run before dod_gate". These run the materializer in-process against
scratch roots; `tests/integration/test_helper_fetch_scenario336.py` runs the real
setup step, which fetches a checkout and calls the same `main` from it.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_helper_materialize as subject
from livespec_orchestrator_beads_fabro.commands import _dispatcher_helper_registry as registry
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner

_REPOSITORY = "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"
_COMMIT = "37e012335ed23ecba9bbcbb829e0fc90f2fdaf3b"
_CAUSE = "LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH"


def _missing() -> bytes:
    return (Path("/nonexistent") / "helper.py").read_bytes()


def _fake_helpers() -> tuple[registry.Helper, ...]:
    return (
        registry.Helper(
            name="runner",
            root=registry.PLUGINS_ROOT,
            path="livespec-runner.py",
            mode=0o644,
            compose=lambda: b"print('runner')\n",
        ),
        registry.Helper(
            name="push",
            root=registry.PLUGINS_ROOT,
            path="bin/livespec-push",
            mode=0o700,
            compose=lambda: b"#!/bin/sh\nexit 0\n",
        ),
        registry.Helper(
            name="guard",
            root=registry.LIVESPEC_ROOT,
            path="guard.sh",
            mode=0o755,
            compose=lambda: b"#!/bin/sh\n",
        ),
    )


def _roots(*, base: Path) -> dict[str, Path]:
    return {name: base / name for name in registry.HELPER_ROOTS}


def _manifest(*, helpers: tuple[registry.Helper, ...]) -> dict[str, object]:
    return registry.helper_manifest(repository=_REPOSITORY, commit=_COMMIT, helpers=helpers)


@pytest.fixture(name="fake_registry")
def _fake_registry(monkeypatch: pytest.MonkeyPatch) -> tuple[registry.Helper, ...]:
    helpers = _fake_helpers()
    monkeypatch.setattr(registry, "helper_registry", lambda: helpers)
    return helpers


def _entries(manifest: dict[str, object]) -> list[dict[str, object]]:
    helpers = manifest["helpers"]
    assert isinstance(helpers, list)
    return helpers  # type: ignore[return-value]


def test_every_real_helper_lands_byte_identical_with_its_mode(tmp_path: Path) -> None:
    roots = _roots(base=tmp_path)
    manifest_text = registry.helper_manifest_text(repository=_REPOSITORY, commit=_COMMIT)
    written = subject.materialize(manifest_text=manifest_text, roots=roots)
    helpers = registry.helper_registry()
    assert written == len(helpers)
    for helper in helpers:
        target = roots[helper.root] / helper.path
        assert target.read_bytes() == helper.compose(), helper.name
        assert target.stat().st_mode & 0o7777 == helper.mode, helper.name
    again = subject.materialize(manifest_text=manifest_text, roots=roots)
    assert again == len(helpers)


def test_main_reports_the_count_and_exits_zero(
    tmp_path: Path, fake_registry: tuple[registry.Helper, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [f"{name}={path}" for name, path in _roots(base=tmp_path).items()]
    status = subject.main(argv=argv, manifest_text=json.dumps(_manifest(helpers=fake_registry)))
    assert status == 0
    assert "wrote and verified 3 helper programs" in capsys.readouterr().err


def test_a_digest_that_differs_fails_naming_the_helper_and_writes_nothing(
    tmp_path: Path, fake_registry: tuple[registry.Helper, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _manifest(helpers=fake_registry)
    _entries(manifest)[1]["sha256"] = "0" * 64
    argv = [f"{name}={path}" for name, path in _roots(base=tmp_path).items()]
    status = subject.main(argv=argv, manifest_text=json.dumps(manifest))
    assert status == 1
    error = capsys.readouterr().err
    assert error.startswith(f"{_CAUSE}: push: composed digest ")
    assert f"at commit {_COMMIT} differs from the manifest's {'0' * 64}" in error
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("mode", 0o755, "manifest mode 493 differs from the registry's 644"),
        ("path", "elsewhere.py", "manifest places it at plugins:elsewhere.py"),
        ("root", "gh-refresh", "manifest places it at gh-refresh:livespec-runner.py"),
    ],
)
def test_a_manifest_entry_the_registry_does_not_place_that_way_is_refused(
    tmp_path: Path,
    fake_registry: tuple[registry.Helper, ...],
    field: str,
    value: object,
    reason: str,
) -> None:
    manifest = _manifest(helpers=fake_registry)
    _entries(manifest)[0][field] = value
    refusal = subject.materialize(manifest_text=json.dumps(manifest), roots=_roots(base=tmp_path))
    assert isinstance(refusal, subject.MaterializeRefusal)
    assert refusal.helper == "runner"
    assert reason in refusal.reason


def test_a_helper_the_commit_cannot_compose_is_a_missing_source_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    present = _fake_helpers()
    manifest = _manifest(helpers=present)
    broken = (
        present[0],
        registry.Helper(
            name="push",
            root=registry.PLUGINS_ROOT,
            path="bin/livespec-push",
            mode=0o700,
            compose=_missing,
        ),
        present[2],
    )
    monkeypatch.setattr(registry, "helper_registry", lambda: broken)
    refusal = subject.materialize(manifest_text=json.dumps(manifest), roots=_roots(base=tmp_path))
    assert isinstance(refusal, subject.MaterializeRefusal)
    assert refusal.line().startswith(f"{_CAUSE}: push: source path missing at commit {_COMMIT}: ")
    assert "/nonexistent/helper.py" in refusal.reason


def test_a_helper_the_commit_does_not_register_is_a_missing_source_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(helpers=_fake_helpers())
    monkeypatch.setattr(registry, "helper_registry", lambda: _fake_helpers()[:1])
    refusal = subject.materialize(manifest_text=json.dumps(manifest), roots=_roots(base=tmp_path))
    assert refusal == subject.MaterializeRefusal(
        helper="push", reason=f"source path missing at commit {_COMMIT}: no such helper"
    )


def test_a_helper_the_manifest_does_not_name_is_refused(
    tmp_path: Path, fake_registry: tuple[registry.Helper, ...]
) -> None:
    manifest = _manifest(helpers=fake_registry[:2])
    refusal = subject.materialize(manifest_text=json.dumps(manifest), roots=_roots(base=tmp_path))
    assert refusal == subject.MaterializeRefusal(
        helper="guard", reason=f"composed at commit {_COMMIT} but not in the helper manifest"
    )


def test_a_helper_whose_root_was_not_resolved_is_refused(
    tmp_path: Path, fake_registry: tuple[registry.Helper, ...]
) -> None:
    roots = {registry.PLUGINS_ROOT: tmp_path / "plugins"}
    manifest = _manifest(helpers=fake_registry)
    refusal = subject.materialize(manifest_text=json.dumps(manifest), roots=roots)
    assert refusal == subject.MaterializeRefusal(
        helper="guard", reason="its sandbox root 'livespec' was not resolved"
    )


def test_a_registry_that_does_not_import_at_the_commit_is_refused(
    tmp_path: Path, fake_registry: tuple[registry.Helper, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subject, "_REGISTRY_MODULE", "livespec_orchestrator_beads_fabro.absent")
    manifest = json.dumps(_manifest(helpers=fake_registry))
    refusal = subject.materialize(manifest_text=manifest, roots=_roots(base=tmp_path))
    assert isinstance(refusal, subject.MaterializeRefusal)
    assert refusal.helper == "helper-registry"
    assert f"does not import at commit {_COMMIT}" in refusal.reason


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("not json", "is not JSON"),
        ("[]", "names no commit and no helper list"),
        ('{"commit": "c"}', "names no commit and no helper list"),
        ('{"helpers": []}', "names no commit and no helper list"),
    ],
)
def test_an_unreadable_manifest_is_refused(tmp_path: Path, text: str, reason: str) -> None:
    refusal = subject.materialize(manifest_text=text, roots=_roots(base=tmp_path))
    assert isinstance(refusal, subject.MaterializeRefusal)
    assert refusal.helper == "helper-manifest"
    assert reason in refusal.reason


@pytest.mark.parametrize("argument", ["plugins", "=/abs", "plugins=relative/path"])
def test_a_root_argument_that_is_not_an_absolute_assignment_is_refused(
    argument: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert subject.main(argv=[argument], manifest_text="{}") == 1
    assert capsys.readouterr().err.startswith(f"{_CAUSE}: helper-manifest: sandbox root argument")


def test_a_written_mode_the_filesystem_did_not_keep_is_refused(
    tmp_path: Path, fake_registry: tuple[registry.Helper, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    def kept_mode(self: Path, mode: int) -> None:
        _ = (self, mode)

    monkeypatch.setattr(Path, "chmod", kept_mode)
    manifest = json.dumps(_manifest(helpers=fake_registry))
    refusal = subject.materialize(manifest_text=manifest, roots=_roots(base=tmp_path))
    assert refusal == subject.MaterializeRefusal(
        helper="runner", reason="written with mode 600, not the manifest's 644"
    )


class _NoCommonDirRunner:
    """The real runner, except that git cannot name the repository's common directory."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        if "--git-common-dir" in argv:
            return CommandResult(exit_code=128, stdout="", stderr="not a git repository")
        return ShellCommandRunner().run(
            argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
        )


def _git(*args: str, cwd: Path) -> None:
    _ = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_a_root_inside_the_runs_worktree_is_excluded_file_by_file(
    tmp_path: Path, fake_registry: tuple[registry.Helper, ...]
) -> None:
    clone = tmp_path / "workspace"
    clone.mkdir()
    _git("init", "-q", cwd=clone)
    roots = {
        registry.PLUGINS_ROOT: tmp_path / "home" / "plugins",
        registry.GH_REFRESH_ROOT: clone / ".livespec-gh-refresh",
        registry.LIVESPEC_ROOT: clone / ".livespec",
    }
    manifest = json.dumps(_manifest(helpers=fake_registry))
    assert subject.materialize(manifest_text=manifest, roots=roots) == len(fake_registry)
    assert subject.materialize(manifest_text=manifest, roots=roots) == len(fake_registry)
    exclude = (clone / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    assert exclude.count("/.livespec/guard.sh") == 1
    assert not any("plugins" in line for line in exclude)
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=clone,
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""


def test_a_worktree_whose_git_directory_cannot_be_read_writes_no_entry(
    tmp_path: Path, fake_registry: tuple[registry.Helper, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = tmp_path / "workspace"
    clone.mkdir()
    _git("init", "-q", cwd=clone)
    monkeypatch.setattr(subject, "ShellCommandRunner", _NoCommonDirRunner)
    roots = {name: clone / name for name in registry.HELPER_ROOTS}
    manifest = json.dumps(_manifest(helpers=fake_registry))
    assert subject.materialize(manifest_text=manifest, roots=roots) == len(fake_registry)
    exclude = clone / ".git" / "info" / "exclude"
    assert not exclude.is_file() or "guard.sh" not in exclude.read_text(encoding="utf-8")


def test_every_root_inside_one_worktree_shares_its_exclude_file(
    tmp_path: Path, fake_registry: tuple[registry.Helper, ...]
) -> None:
    clone = tmp_path / "workspace"
    clone.mkdir()
    _git("init", "-q", cwd=clone)
    roots = {name: clone / f".{name}" for name in registry.HELPER_ROOTS}
    manifest = json.dumps(_manifest(helpers=fake_registry))
    assert subject.materialize(manifest_text=manifest, roots=roots) == len(fake_registry)
    exclude = (clone / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    assert {
        "/.plugins/livespec-runner.py",
        "/.plugins/bin/livespec-push",
        "/.livespec/guard.sh",
    } <= (set(exclude))


class _NoWorktreeRunner:
    """A git that finds no worktree anywhere, as on a plugins root outside every clone."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(exit_code=128, stdout="", stderr="not a git repository")


def test_a_root_outside_every_worktree_is_written_and_excluded_nowhere(
    tmp_path: Path, fake_registry: tuple[registry.Helper, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subject, "ShellCommandRunner", _NoWorktreeRunner)
    manifest = json.dumps(_manifest(helpers=fake_registry))
    roots = _roots(base=tmp_path / "outside")
    assert subject.materialize(manifest_text=manifest, roots=roots) == len(fake_registry)
    assert (roots[registry.LIVESPEC_ROOT] / "guard.sh").read_bytes() == b"#!/bin/sh\n"
