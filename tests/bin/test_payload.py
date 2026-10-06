"""Tests for .claude-plugin/scripts/bin/_payload.py.

Unit coverage for the launcher's payload-retention decisions: which plugin
roots are harness-managed, that each invocation gets a payload no other
invocation shares, that no pre-existing tree is ever adopted as one, which
sources are refused as incomplete, that a failed or truncated copy cleans up
after itself, and how a release LABEL degrades when a present manifest cannot
be parsed.

Each call supplies its own isolated `environ` mapping, so a unit case can
never adopt a payload another case published.

The end-to-end counterparts can only be asked of real child processes:
`test_payload_retention_after_eviction.py` (what a live process sees after its
installation is deleted underneath it),
`test_payload_concurrent_release_isolation.py` (two concurrent invocations
keeping their own releases), and `test_payload_provisioning_refusal.py` (that a
refusal reaches the real CLI before any claim).
"""

import importlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"
_RELEASE = "9.9.9"
_UNKNOWN_RELEASE = "unknown-release"
_HOLDER_PREFIX = "livespec-orchestrator-beads-fabro-payload-"
# What a SOURCE CHECKOUT of this plugin looks like: the plugin root keeps the
# name a checkout gives it, and the tree above it names THIS project.
_CHECKOUT_PLUGIN_ROOT = ".claude-plugin"
_THIS_PROJECT = '[project]\nname = "livespec-orchestrator-beads-fabro"\n'


def _checkout(*, root: Path) -> Path:
    """A tree that is identifiably THIS plugin's own source checkout."""
    _ = (root / "pyproject.toml").write_text(_THIS_PROJECT, encoding="utf-8")
    return root / _CHECKOUT_PLUGIN_ROOT


# Every member `_payload` requires of a usable payload, as the relative path
# its refusal names.
_REQUIRED = (
    "plugin.json",
    "scripts/bin/_bootstrap.py",
    "scripts/bin/_payload.py",
    "scripts/livespec_orchestrator_beads_fabro/__init__.py",
    "scripts/_vendor",
    ".fabro/workflows",
)


def _import_payload() -> Any:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    _ = sys.modules.pop("_payload", None)
    return importlib.import_module("_payload")


def _install(*, root: Path, manifest: str = f'{{"version": "{_RELEASE}"}}') -> Path:
    """A COMPLETE minimal installed plugin root, plus a stale cache to be dropped.

    "Complete" is type- and emptiness-aware since `_payload` stopped grading
    with `exists()`: the required TREES must be directories that hold
    something, so each gets a file, and the required FILES must be files.
    """
    for relative in (
        "scripts/bin",
        "scripts/livespec_orchestrator_beads_fabro/commands",
        "scripts/_vendor/livespec_runtime",
        ".fabro/workflows/implement-work-item",
        "scripts/__pycache__",
    ):
        (root / relative).mkdir(parents=True)
    for relative in (
        "scripts/bin/_bootstrap.py",
        "scripts/bin/_payload.py",
        "scripts/livespec_orchestrator_beads_fabro/__init__.py",
        "scripts/livespec_orchestrator_beads_fabro/commands/__init__.py",
        "scripts/_vendor/livespec_runtime/__init__.py",
        ".fabro/workflows/implement-work-item/workflow.toml",
        "scripts/__pycache__/stale.pyc",
    ):
        _ = (root / relative).write_text("", encoding="utf-8")
    _ = (root / "plugin.json").write_text(manifest, encoding="utf-8")
    return root


def _private_tempdir(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point `tempfile` at a per-test directory so holders are observable."""
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    return temp_root


def test_this_projects_own_checkout_is_not_harness_managed(tmp_path: Path) -> None:
    """Both conditions hold: the plugin-root name, and a pyproject naming us."""
    payload = _import_payload()
    assert payload.harness_managed(source_root=_checkout(root=tmp_path)) is False


@pytest.mark.parametrize(
    ("description", "project_file"),
    [
        pytest.param("a stranger's project", '[project]\nname = "unrelated"\n', id="other-project"),
        pytest.param("no project file at all", None, id="absent"),
    ],
)
def test_a_plugin_root_beside_something_that_is_not_this_project_is_harness_managed(
    tmp_path: Path, description: str, project_file: str | None
) -> None:
    """Presence of SOME project file is not proof of this checkout.

    An installed tree can sit beside anything. Treating any neighbour as
    proof switched retention off for a real install and put the invocation
    back on an evictable source — silently, which is the direction that
    re-opens the defect.
    """
    payload = _import_payload()
    if project_file is not None:
        _ = (tmp_path / "pyproject.toml").write_text(project_file, encoding="utf-8")
    assert (
        payload.harness_managed(source_root=tmp_path / _CHECKOUT_PLUGIN_ROOT) is True
    ), f"retention was disabled by {description}"


def test_a_justfile_alone_no_longer_exempts_a_tree(tmp_path: Path) -> None:
    """The old weak marker: a `justfile` used to be enough on its own."""
    payload = _import_payload()
    _ = (tmp_path / "justfile").write_text("default:\n", encoding="utf-8")
    assert payload.harness_managed(source_root=tmp_path / _CHECKOUT_PLUGIN_ROOT) is True


def test_a_differently_named_root_beside_our_pyproject_is_harness_managed(
    tmp_path: Path,
) -> None:
    """An install flattens the plugin root to a build-named cache directory.

    So our own `pyproject.toml` above it is not enough either — a cache can be
    unpacked anywhere, including inside a checkout.
    """
    payload = _import_payload()
    _ = (tmp_path / "pyproject.toml").write_text(_THIS_PROJECT, encoding="utf-8")
    assert payload.harness_managed(source_root=tmp_path / "abc123def456") is True


def test_an_unreadable_project_file_is_not_taken_as_proof_of_a_checkout(
    tmp_path: Path,
) -> None:
    """Unreadable means unproven, and unproven means retain."""
    payload = _import_payload()
    (tmp_path / "pyproject.toml").mkdir()
    assert payload.harness_managed(source_root=tmp_path / _CHECKOUT_PLUGIN_ROOT) is True


def test_a_checkout_plugin_root_is_its_own_payload(tmp_path: Path) -> None:
    """The one case that copies nothing: the operator's tree is left alone.

    It is also NOT validated. A checkout is not provisioned, so there is no
    provision to refuse, and holding a developer's working tree to a released
    payload's completeness contract would refuse mid-edit.
    """
    payload = _import_payload()
    source_root = _checkout(root=tmp_path)
    source_root.mkdir()
    retained = payload.retain_payload(source_root=source_root, environ={})
    assert retained.retained is False
    assert retained.root == source_root
    assert retained.scripts_root == source_root / "scripts"
    assert retained.vendor_root == source_root / "scripts" / "_vendor"


def test_an_installed_plugin_root_is_copied_into_a_private_holder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    retained = payload.retain_payload(source_root=source_root, environ={})
    assert retained.retained is True
    assert retained.root.parent.parent == temp_root
    # The release LABELS the holder for a human reading /tmp; it is not identity.
    assert retained.root.parent.name.startswith(f"{_HOLDER_PREFIX}{_RELEASE}-")
    assert (retained.scripts_root / "livespec_orchestrator_beads_fabro").is_dir()
    assert retained.vendor_root.is_dir()
    assert not (
        retained.scripts_root / "__pycache__"
    ).exists(), "byte-compiled caches are reproducible and must not be carried into the payload"


def test_each_invocation_gets_a_payload_no_other_invocation_shares(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two retentions of the SAME release must not resolve the same tree."""
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    first = payload.retain_payload(source_root=source_root, environ={})
    second = payload.retain_payload(source_root=source_root, environ={})
    assert first.root != second.root
    # A write into one payload must be invisible to the other — the property a
    # shared release-keyed directory could not provide.
    _ = (first.root / "witness").write_text("first", encoding="utf-8")
    assert not (second.root / "witness").exists()


def test_a_pre_existing_tree_at_a_guessable_path_is_never_adopted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Adoption is structurally impossible: no existing path is consulted.

    The decoys are the ones a guessable, release-keyed payload path invited —
    a complete-looking foreign tree, reached through a symlink, planted under
    the exact prefix the launcher labels its holders with. Neither the foreign
    code nor the symlink may end up in the executable payload.
    """
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    foreign = _install(root=tmp_path / "foreign")
    _ = (foreign / "scripts" / "SMOKING-GUN").write_text("adopted", encoding="utf-8")
    decoy = temp_root / f"{_HOLDER_PREFIX}{_RELEASE}"
    decoy.mkdir()
    (decoy / "payload").symlink_to(foreign, target_is_directory=True)

    source_root = _install(root=tmp_path / "cache" / "abc123")
    retained = payload.retain_payload(source_root=source_root, environ={})
    assert retained.root.parent != decoy
    assert not retained.root.is_symlink()
    assert not (
        retained.scripts_root / "SMOKING-GUN"
    ).exists(), "the launcher adopted a pre-existing tree as its executable payload"


@pytest.mark.parametrize("absent", _REQUIRED)
def test_a_source_missing_any_required_member_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, absent: str
) -> None:
    """Each required member, removed on its own, must be named in the refusal."""
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    target = source_root.joinpath(*absent.split("/"))
    shutil.rmtree(target) if target.is_dir() else target.unlink()

    refusal = payload.retain_payload(source_root=source_root, environ={})
    assert isinstance(refusal, payload.PayloadRefusal)
    assert absent in refusal.message
    assert str(source_root) in refusal.message
    assert "Nothing was claimed" in refusal.message
    assert list(temp_root.iterdir()) == [], "a refused provision created a holder anyway"


def test_a_copy_that_fails_is_refused_and_leaves_no_holder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dangling symlink makes the real copy fail part-way; the holder must go."""
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    (source_root / "scripts" / "dangling-link").symlink_to(tmp_path / "nothing-here")

    refusal = payload.retain_payload(source_root=source_root, environ={})
    assert isinstance(refusal, payload.PayloadRefusal)
    assert "copying the installed release" in refusal.message
    assert str(source_root) in refusal.message
    assert list(temp_root.iterdir()) == [], "the failed copy left its holder behind"


def test_a_copy_that_silently_truncates_is_refused_and_leaves_no_holder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A copy can SUCCEED and still be incomplete — the eviction-mid-provision case.

    The source passed its own completeness check moments earlier, so a copy
    that lands short means the source changed underneath it. `copytree` is
    replaced with one that reports success while writing almost nothing, which
    is the only way to reach that arm deterministically.
    """
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")

    def _truncating_copytree(_source: Path, destination: Path, **_kwargs: object) -> Path:
        destination.mkdir(parents=True)
        _ = (destination / "plugin.json").write_text("{}", encoding="utf-8")
        return destination

    monkeypatch.setattr(payload.shutil, "copytree", _truncating_copytree)
    refusal = payload.retain_payload(source_root=source_root, environ={})
    assert isinstance(refusal, payload.PayloadRefusal)
    assert "copy at" in refusal.message
    assert "scripts/_vendor" in refusal.message
    assert list(temp_root.iterdir()) == [], "the truncated copy left its holder behind"


@pytest.mark.parametrize(
    "manifest",
    [
        pytest.param("{not json", id="malformed"),
        pytest.param("[]", id="not-an-object"),
        pytest.param("{}", id="no-version-key"),
        pytest.param('{"version": 7}', id="version-not-a-string"),
        pytest.param('{"version": "   "}', id="version-blank"),
    ],
)
def test_an_unusable_release_manifest_is_refused_naming_its_fault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, manifest: str
) -> None:
    """A manifest present but unusable is a PROVENANCE fault, not a cosmetic one.

    These cases used to degrade to the placeholder `unknown-release` and
    provision anyway. A payload whose own release cannot be established cannot
    be compared against another build, which is what the minimum-release floor
    and the build-currency findings do, so the placeholder left "which build is
    this" unanswerable while those surfaces kept answering.
    """
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123", manifest=manifest)

    refusal = payload.retain_payload(source_root=source_root, environ={})
    assert isinstance(refusal, payload.PayloadRefusal)
    assert "plugin.json" in refusal.message
    assert str(source_root) in refusal.message
    assert "Nothing was claimed" in refusal.message
    assert (
        _UNKNOWN_RELEASE not in refusal.message
    ), "the refusal still reports a placeholder release"
    assert (
        list(temp_root.iterdir()) == []
    ), "a provenance refusal created a private directory before refusing"


def test_a_manifest_that_is_a_directory_is_refused_as_incomplete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A DIRECTORY named `plugin.json` is a TYPE fault, caught before the read.

    This case used to reach the provenance read and be refused there. Since
    completeness became type-aware it is refused one step earlier, as an
    incomplete installation — which is the better place: a directory where a
    module or manifest belongs is a broken install, not a broken manifest.
    """
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    (source_root / "plugin.json").unlink()
    (source_root / "plugin.json").mkdir()

    refusal = payload.retain_payload(source_root=source_root, environ={})
    assert isinstance(refusal, payload.PayloadRefusal)
    assert "plugin.json" in refusal.message
    assert "is missing" in refusal.message
    assert list(temp_root.iterdir()) == []


def test_a_manifest_whose_read_itself_fails_is_refused_naming_that_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A real I/O error on the read — EIO, a vanished mount — not a type fault.

    It cannot be produced from a fixture: the suite runs as a uid that reads
    mode-000 files, and anything the filesystem WILL refuse also fails the
    type grade one step earlier. So the read itself is driven to fail, which
    is the same technique `test_bootstrap.py` uses for its exit-127 arm rather
    than a coverage pragma. Without this the launcher would turn a transient
    read error into a traceback instead of an actionable refusal.
    """
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")

    def _failing_read_text(self: Path, *args: object, **kwargs: object) -> str:
        # The manifest is the only text this path reads, so no name guard is
        # needed — and a guard would add a branch nothing exercises.
        _ = (self, args, kwargs)
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(Path, "read_text", _failing_read_text)
    refusal = payload.retain_payload(source_root=source_root, environ={})
    assert isinstance(refusal, payload.PayloadRefusal)
    assert "could not be read" in refusal.message
    assert "Input/output error" in refusal.message
    assert (
        list(temp_root.iterdir()) == []
    ), "a provenance refusal created a private directory before refusing"


def test_a_child_inherits_its_parents_payload_and_does_not_own_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One dispatch is several processes; they must all read the same tree."""
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    environ: dict[str, str] = {}
    parent = payload.retain_payload(source_root=source_root, environ=environ)
    assert environ[payload.PAYLOAD_ROOT_ENV] == str(parent.root)

    child = payload.retain_payload(source_root=source_root, environ=dict(environ))
    assert child.root == parent.root
    assert child.retained is True
    assert child.holder is None, "an inherited payload must not be owned by the child"
    assert len(list(temp_root.iterdir())) == 1, "the child provisioned a copy of the copy"


def test_an_inherited_payload_that_is_gone_falls_through_to_a_fresh_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A parent that already exited and cleaned up must not strand its child.

    Nothing is adopted on trust: the inherited tree passes the same
    completeness contract a fresh copy must pass, or it is not executed.
    """
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    stale = tmp_path / "already-released"
    stale.mkdir()

    retained = payload.retain_payload(
        source_root=source_root, environ={payload.PAYLOAD_ROOT_ENV: str(stale)}
    )
    assert retained.root != stale
    assert retained.holder is not None
    assert retained.vendor_root.is_dir()


def test_releasing_an_owned_payload_removes_its_holder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    retained = payload.retain_payload(source_root=source_root, environ={})
    assert retained.root.is_dir()

    payload.release_payload(payload=retained)
    assert not retained.root.exists()
    assert list(temp_root.iterdir()) == [], "the holder outlived the payload it held"


@pytest.mark.parametrize("case", ["checkout", "inherited"])
def test_releasing_a_payload_this_process_does_not_own_removes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str
) -> None:
    """The two unowned shapes: an operator's checkout, and a parent's payload."""
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    if case == "checkout":
        source_root = _install(root=_checkout(root=tmp_path))
        unowned = payload.retain_payload(source_root=source_root, environ={})
    else:
        source_root = _install(root=tmp_path / "cache" / "abc123")
        owner_environ: dict[str, str] = {}
        owned = payload.retain_payload(source_root=source_root, environ=owner_environ)
        source_root = _install(root=tmp_path / "cache" / "def456")
        unowned = payload.retain_payload(source_root=source_root, environ=dict(owner_environ))
        assert unowned.root == owned.root

    assert unowned.holder is None
    payload.release_payload(payload=unowned)
    assert unowned.root.is_dir(), "a release removed a tree this process never created"


def test_the_re_exec_argv_is_re_pointed_at_the_payloads_own_copy(tmp_path: Path) -> None:
    """The program moves to its counterpart; the operands are left alone."""
    payload = _import_payload()
    source_root = tmp_path / "install"
    payload_root = tmp_path / "payload"
    program = source_root / "scripts" / "bin" / "dispatcher.py"
    program.parent.mkdir(parents=True)
    _ = program.write_text("", encoding="utf-8")

    rewritten = payload.payload_relative_argv(
        argv=[str(program), "loop", "--repo", str(source_root)],
        source_root=source_root,
        payload_root=payload_root,
    )
    assert rewritten[0] == str(payload_root / "scripts" / "bin" / "dispatcher.py")
    # Operands belong to the caller and may legitimately name the evicted tree.
    assert rewritten[1:] == ["loop", "--repo", str(source_root)]


@pytest.mark.parametrize("argv", [[], ["-c", "print(1)"], ["/elsewhere/other.py"]])
def test_an_argv_with_no_counterpart_in_the_payload_is_unchanged(
    tmp_path: Path, argv: list[str]
) -> None:
    """Empty argv, a `-c` invocation, and a program in some other tree."""
    payload = _import_payload()
    assert (
        payload.payload_relative_argv(
            argv=argv, source_root=tmp_path / "install", payload_root=tmp_path / "payload"
        )
        == argv
    )


def test_an_unresolvable_program_path_leaves_the_argv_unchanged(tmp_path: Path) -> None:
    """A cosmetic path fault must not become a dead launcher.

    A symlink loop is the one unresolvable shape that is deterministic on
    every supported interpreter; which exception `resolve()` raises for it
    differs by version, which is why the handler names all three.
    """
    payload = _import_payload()
    source_root = tmp_path / "install"
    source_root.mkdir()
    (tmp_path / "loop-a").symlink_to(tmp_path / "loop-b")
    (tmp_path / "loop-b").symlink_to(tmp_path / "loop-a")

    argv = [str(tmp_path / "loop-a"), "loop"]
    assert (
        payload.payload_relative_argv(
            argv=argv, source_root=source_root, payload_root=tmp_path / "payload"
        )
        == argv
    )


def test_fidelity_reports_a_file_the_copy_lacks_and_one_that_is_short(tmp_path: Path) -> None:
    """Absence and truncation are the two ways a copy stops being its source."""
    payload = _import_payload()
    source_root = _install(root=tmp_path / "source")
    _ = (source_root / "scripts" / "livespec_orchestrator_beads_fabro" / "deferred.py").write_text(
        "DEFERRED = 1\n", encoding="utf-8"
    )
    copy_root = tmp_path / "copy"
    _ = shutil.copytree(source_root, copy_root)
    (copy_root / "scripts" / "livespec_orchestrator_beads_fabro" / "deferred.py").unlink()
    _ = (copy_root / "plugin.json").write_text("", encoding="utf-8")

    gaps = payload.payload_fidelity_gaps(source_root=source_root, payload_root=copy_root)
    assert "scripts/livespec_orchestrator_beads_fabro/deferred.py" in gaps
    assert "plugin.json" in gaps


def test_fidelity_ignores_what_the_copy_deliberately_drops(tmp_path: Path) -> None:
    """`__pycache__` is excluded from the copy, so it must not read as a gap."""
    payload = _import_payload()
    source_root = _install(root=tmp_path / "source")
    copy_root = tmp_path / "copy"
    _ = shutil.copytree(source_root, copy_root, ignore=shutil.ignore_patterns("__pycache__"))
    assert (source_root / "scripts" / "__pycache__" / "stale.pyc").is_file()
    assert payload.payload_fidelity_gaps(source_root=source_root, payload_root=copy_root) == ()


def test_a_fidelity_report_is_capped_and_says_so(tmp_path: Path) -> None:
    """An operator needs enough paths to recognise the fault, not all of them."""
    payload = _import_payload()
    source_root = _install(root=tmp_path / "source")
    for index in range(12):
        _ = (source_root / f"extra-{index}.txt").write_text("x", encoding="utf-8")
    copy_root = tmp_path / "copy"
    copy_root.mkdir()

    gaps = payload.payload_fidelity_gaps(source_root=source_root, payload_root=copy_root)
    assert len(gaps) == 5, f"the report was not capped: {gaps}"
    assert "possibly more" in payload._fidelity_message(root=source_root, gaps=gaps)  # noqa: SLF001


def test_a_copy_that_lands_short_refuses_and_leaves_no_holder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The in-process counterpart of the short-copy CLI case.

    The product's own `ignore_patterns` seam is wrapped so the real copy skips
    one deferred module — the shape of a copy truncated by an eviction landing
    mid-provision.
    """
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "abc123")
    _ = (
        source_root / "scripts" / "livespec_orchestrator_beads_fabro" / "commands" / "deferred.py"
    ).write_text("DEFERRED = 1\n", encoding="utf-8")
    real_ignore = payload.shutil.ignore_patterns
    monkeypatch.setattr(
        payload.shutil, "ignore_patterns", lambda *names: real_ignore(*names, "deferred.py")
    )

    refusal = payload.retain_payload(source_root=source_root, environ={})
    assert isinstance(refusal, payload.PayloadRefusal)
    assert "did not land complete" in refusal.message
    assert "deferred.py" in refusal.message
    assert "DIFFERENT release" in refusal.message
    assert list(temp_root.iterdir()) == [], "the short copy left its holder behind"


def test_an_unusable_temporary_destination_is_refused_not_raised(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`mkdtemp` sits inside the handler, like every other provisioning step.

    `TMPDIR` cannot drive this — `tempfile` falls back past an unusable one —
    so the destination is PINNED, which is the seam an embedder sets and the
    one the end-to-end case in test_payload_provisioning_boundary.py uses.
    """
    payload = _import_payload()
    not_a_directory = tmp_path / "not-a-directory"
    _ = not_a_directory.write_text("", encoding="utf-8")
    monkeypatch.setattr(tempfile, "tempdir", str(not_a_directory))
    source_root = _install(root=tmp_path / "cache" / "abc123")

    refusal = payload.retain_payload(source_root=source_root, environ={})
    assert isinstance(refusal, payload.PayloadRefusal)
    assert "no private directory could be created" in refusal.message
    assert str(not_a_directory) in refusal.message
    assert "Nothing was claimed" in refusal.message


@pytest.mark.parametrize(
    "version",
    [
        pytest.param("../../escaped", id="parent-traversal"),
        pytest.param("a/b", id="embedded-separator"),
        pytest.param("..", id="parent-reference"),
        pytest.param(".", id="bare-dot"),
        pytest.param(".hidden", id="leading-dot"),
        pytest.param("a\\b", id="backslash"),
        pytest.param("a\x00b", id="nul-byte"),
    ],
)
def test_a_release_label_that_is_not_one_path_segment_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, version: str
) -> None:
    """Raw manifest text must never reach the holder's path as path SYNTAX."""
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(
        root=tmp_path / "cache" / "abc123", manifest=json.dumps({"version": version})
    )

    refusal = payload.retain_payload(source_root=source_root, environ={})
    assert isinstance(refusal, payload.PayloadRefusal)
    assert "not usable as a single path segment" in refusal.message
    assert list(temp_root.iterdir()) == [], "a refused label still created a holder"


def test_an_ordinary_release_label_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control: the segment grade must not reject real release strings."""
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(
        root=tmp_path / "cache" / "abc123", manifest=json.dumps({"version": "1.2.3-rc.4+build5"})
    )

    retained = payload.retain_payload(source_root=source_root, environ={})
    assert retained.retained is True
    assert "1.2.3-rc.4+build5" in retained.root.parent.name
