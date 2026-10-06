"""The Dispatcher resolves its Fabro workflow + bin over a three-step precedence.

Slice 1 of orchestrator-plugin-self-containment established the PLUGIN ROOT as
the anchor: `workflow_toml` and `candidate_dispatcher_bin` resolve against
`.claude-plugin/` in source (or `CLAUDE_PLUGIN_ROOT` in the flattened install
cache) rather than the repo root, and the `.fabro/` workflow payload ships
INSIDE that root.

`workflow_toml` then admits the DISPATCH TARGET's own committed workflow
between the explicit override and that plugin-root default, so a consumer repo
whose sandbox needs a different toolchain governs its own execution substrate.
A named workflow VARIANT, selected from the target's `dispatcher.workflows`
registry, sits between those two: it is a whole directory in the target repo
with no bundle to fall back to. The full precedence under test:

1. An explicit `--workflow <path>` always wins.
2. Otherwise `<repo>/<variant_directory>/workflow.toml`, when this dispatch
   selected a registered variant.
3. Otherwise `<repo>/.fabro/workflows/implement-work-item/workflow.toml`, when
   the dispatch target commits one. `args` is not guaranteed to carry a `repo`
   attribute, so a namespace without one must degrade to step 4 rather than
   raise — and that degradation covers step 2 as well.
4. Otherwise `<plugin-root>/.fabro/workflows/implement-work-item/workflow.toml`,
   where `<plugin-root>` is `Path(dispatcher.__file__).resolve().parents[3]`
   (the `.claude-plugin/` dir) — and the packaged `workflow.toml` AND
   `workflow.fabro` must actually exist there, so a future accidental drop of
   the payload fails CI (the structural guard for change (e)).

Both resolvers honor a non-empty `CLAUDE_PLUGIN_ROOT` env override (the
cache-mode anchor) and otherwise fall back to the source `parents[3]` walk.

The `_config.resolve_workflow_variant` seam that SELECTS a variant is covered
here too, against real `.livespec.jsonc` files, because the precedence it
implements and the precedence `workflow_toml` implements are two halves of one
answer and a reader checking either one wants the other beside it.
"""

from __future__ import annotations

import argparse
import json
from inspect import signature
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _config, dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeCredentialStatus,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_env import (
    check_credential_env,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_wrapper import (
    credential_wrapper_text,
    read_dispatch_target_credential_wrapper,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    executing_payload_root,
    workflow_toml,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    candidate_dispatcher_bin,
)

# The plugin root in source: `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/
# commands/dispatcher.py` → parents[3] is the `.claude-plugin/` dir.
_PLUGIN_ROOT = Path(dispatcher.__file__).resolve().parents[3]
_WORKFLOW_SUBPATH = (".fabro", "workflows", "implement-work-item", "workflow.toml")
_PROMPTS_DIR = _PLUGIN_ROOT / ".fabro" / "workflows" / "implement-work-item" / "prompts"
_REGISTERED_PROMPT_DIRS = (
    _PROMPTS_DIR,
    _PLUGIN_ROOT.parent / ".fabro" / "workflows" / "groom-work-item" / "prompts",
)
_GOAL_PREAMBLE_REFERENCE = "complete work-item goal is in the Fabro-injected `Goal:` preamble"
_TEST_TOKEN = "test-oauth-token"
_VARIANT_DIR = ".fabro/workflows/codex-first"


def _write_dispatcher_config(*, repo: Path, block: dict[str, object]) -> None:
    """Commit a `.livespec.jsonc` carrying only the given dispatcher block."""
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": block}}),
        encoding="utf-8",
    )


def _credential_status(*, token: str, usable: bool) -> ClaudeCredentialStatus:
    assert token == _TEST_TOKEN
    return ClaudeCredentialStatus(
        condition="usable" if usable else "exhausted",
        present=True,
        usable=usable,
        http_status=200 if usable else 429,
        error_type=None if usable else "rate_limit_error",
        input_tokens=9 if usable else None,
        output_tokens=1 if usable else None,
        message=(
            "CLAUDE_CODE_OAUTH_TOKEN is usable."
            if usable
            else "CLAUDE_CODE_OAUTH_TOKEN is exhausted or rate-limited."
        ),
        remedy="No action required." if usable else "Wait before retrying.",
    )


def test_workflow_toml_resolves_from_plugin_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default resolution anchors on the plugin root and the payload ships there."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    resolved = workflow_toml(args=argparse.Namespace(workflow=None))
    assert resolved == _PLUGIN_ROOT.joinpath(*_WORKFLOW_SUBPATH)
    assert resolved.parts[-5:] == (
        ".claude-plugin",
        ".fabro",
        "workflows",
        "implement-work-item",
        "workflow.toml",
    )
    # Structural guard (e): the packaged workflow payload exists at the plugin
    # root — both the TOML manifest and its sibling Fabro phase graph — so an
    # accidental drop of the payload fails CI.
    assert resolved.is_file()
    assert (resolved.parent / "workflow.fabro").is_file()


def test_workflow_toml_resolves_the_bundle_under_the_executing_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The bundled fallback follows the EXECUTING code, not `CLAUDE_PLUGIN_ROOT`.

    This used to assert the opposite — that a non-empty `CLAUDE_PLUGIN_ROOT`
    won — and the change is deliberate, driven by work-item `bd-ib-mtuqxb`
    (`tests/bin/test_payload_candidate_and_credential_boundary.py`). Reading an
    ASSET through the installed-root anchor is what made a dispatch lose its
    workflow payload when the harness evicted the cache mid-run, so asset
    resolution moved to `executing_payload_root`.

    `CLAUDE_PLUGIN_ROOT` itself is NOT retired and is not merely ignored: it
    still answers "which installation is present", which is the question the
    self-update canary, the minimum-release floor and the registered-install
    currency finding ask, and `plugin_root` still reads it — asserted in
    `test_dispatcher_paths.py`. Setting it here and watching the bundled
    manifest ignore it is the assertion that the two questions are now
    separate.
    """
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    resolved = workflow_toml(args=argparse.Namespace(workflow=None))
    assert resolved == executing_payload_root().joinpath(*_WORKFLOW_SUBPATH)
    assert resolved != tmp_path.joinpath(*_WORKFLOW_SUBPATH)
    assert resolved.is_file(), "the bundled workflow must exist under the executing payload"


def test_workflow_override_arg_wins() -> None:
    """An explicit `--workflow <path>` still overrides the plugin-root default."""
    override = "/somewhere/else/workflow.toml"
    assert workflow_toml(args=argparse.Namespace(workflow=override)) == Path(override)


def test_workflow_toml_prefers_the_dispatch_target_committed_workflow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dispatch target that commits its own workflow governs its own sandbox.

    The bundled workflow pins the orchestrator's OWN (Python-only) sandbox
    image; a consumer repo needing another toolchain layer commits its own
    `workflow.toml` and must have it read rather than silently ignored.
    """
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    repo = tmp_path / "consumer-repo"
    repo_local = repo.joinpath(*_WORKFLOW_SUBPATH)
    repo_local.parent.mkdir(parents=True)
    _ = repo_local.write_text("# the dispatch target's own workflow\n", encoding="utf-8")

    resolved = workflow_toml(args=argparse.Namespace(workflow=None, repo=str(repo)))

    assert resolved == repo_local


def test_workflow_toml_falls_back_to_plugin_root_when_repo_commits_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dispatch target committing no workflow keeps the bundled default."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    repo = tmp_path / "consumer-repo"
    repo.mkdir()

    resolved = workflow_toml(args=argparse.Namespace(workflow=None, repo=str(repo)))

    assert resolved == _PLUGIN_ROOT.joinpath(*_WORKFLOW_SUBPATH)


def test_workflow_override_arg_wins_over_the_repo_local_workflow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--workflow` outranks a committed repo-local workflow, not just the default."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    repo = tmp_path / "consumer-repo"
    repo_local = repo.joinpath(*_WORKFLOW_SUBPATH)
    repo_local.parent.mkdir(parents=True)
    _ = repo_local.write_text("# the dispatch target's own workflow\n", encoding="utf-8")
    override = tmp_path / "explicit" / "workflow.toml"

    resolved = workflow_toml(
        args=argparse.Namespace(workflow=str(override), repo=str(repo)),
    )

    assert resolved == override


def test_workflow_toml_resolves_a_selected_variant_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A selected variant's registry directory wins over the reserved workflow.

    The first assertion is the Red-honest guard the new-module stub technique
    prescribes for a parameter that does not exist yet: without it the call
    below would die on a TypeError rather than on a behavioural assertion, and
    a Red that only proves a signature is unimportable proves nothing about
    the behaviour. It stays because it is also the cheapest statement of the
    contract this whole file documents — the variant directory is an INPUT.
    """
    assert "variant_directory" in signature(workflow_toml).parameters
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    repo = tmp_path / "consumer-repo"
    # The target ALSO commits the reserved workflow, so a resolution that
    # ignored the variant would still return a real, existing file — the
    # failure mode this test exists to catch.
    reserved = repo.joinpath(*_WORKFLOW_SUBPATH)
    reserved.parent.mkdir(parents=True)
    _ = reserved.write_text("# the reserved workflow\n", encoding="utf-8")

    resolved = workflow_toml(
        args=argparse.Namespace(workflow=None, repo=str(repo)),
        variant_directory=_VARIANT_DIR,
    )

    assert resolved == repo / _VARIANT_DIR / "workflow.toml"


def test_workflow_toml_does_not_fall_back_from_a_selected_variant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A variant is a whole directory: an absent one does NOT fall back.

    `_dispatcher_workflow_variant` has already refused an incomplete registry
    directory before this point, so re-probing here could only re-introduce
    the silent substitution the refusal exists to prevent.
    """
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    repo = tmp_path / "consumer-repo"
    repo.mkdir()

    resolved = workflow_toml(
        args=argparse.Namespace(workflow=None, repo=str(repo)),
        variant_directory=_VARIANT_DIR,
    )

    assert resolved == repo / _VARIANT_DIR / "workflow.toml"
    assert not resolved.is_file()


def test_workflow_override_arg_wins_over_a_selected_variant(tmp_path: Path) -> None:
    """`--workflow` outranks every registry choice, not just the two defaults."""
    override = tmp_path / "explicit" / "workflow.toml"

    resolved = workflow_toml(
        args=argparse.Namespace(workflow=str(override), repo=str(tmp_path)),
        variant_directory=_VARIANT_DIR,
    )

    assert resolved == override


def test_workflow_toml_degrades_a_variant_without_a_repo_to_the_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A variant directory with no repo to anchor it degrades, never raises."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    args = argparse.Namespace(workflow=None)
    assert not hasattr(args, "repo")

    resolved = workflow_toml(args=args, variant_directory=_VARIANT_DIR)

    assert resolved == _PLUGIN_ROOT.joinpath(*_WORKFLOW_SUBPATH)


def test_workflow_toml_without_a_variant_resolves_exactly_as_before(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The no-registry case is byte-identical to the pre-registry behaviour.

    Both repo-local arms are exercised against the SAME namespace the caller
    passed before the parameter existed, so a target declaring no registry
    cannot have its resolution moved by this change.
    """
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    repo = tmp_path / "consumer-repo"
    repo.mkdir()
    args = argparse.Namespace(workflow=None, repo=str(repo))

    assert workflow_toml(args=args) == _PLUGIN_ROOT.joinpath(*_WORKFLOW_SUBPATH)

    repo_local = repo.joinpath(*_WORKFLOW_SUBPATH)
    repo_local.parent.mkdir(parents=True)
    _ = repo_local.write_text("# the dispatch target's own workflow\n", encoding="utf-8")

    assert workflow_toml(args=args) == repo_local


def test_resolve_workflow_variant_defaults_to_the_reserved_name(tmp_path: Path) -> None:
    """A target declaring no registry selects the reserved workflow."""
    assert hasattr(_config, "resolve_workflow_variant")

    variant = _config.resolve_workflow_variant(cwd=tmp_path)

    assert variant.name == "implement-work-item"
    assert variant.directory is None


def test_resolve_workflow_variant_reads_the_configured_default(tmp_path: Path) -> None:
    """`dispatcher.default_workflow` selects a registered entry from the config file."""
    _write_dispatcher_config(
        repo=tmp_path,
        block={"workflows": {"codex-first": _VARIANT_DIR}, "default_workflow": "codex-first"},
    )

    variant = _config.resolve_workflow_variant(cwd=tmp_path)

    assert variant.name == "codex-first"
    assert variant.directory == _VARIANT_DIR


def test_resolve_workflow_variant_prefers_an_explicit_name(tmp_path: Path) -> None:
    """An explicitly named variant outranks the configured default."""
    _write_dispatcher_config(
        repo=tmp_path,
        block={
            "workflows": {"codex-first": _VARIANT_DIR, "review-heavy": ".fabro/workflows/rh"},
            "default_workflow": "codex-first",
        },
    )

    variant = _config.resolve_workflow_variant(cwd=tmp_path, name="review-heavy")

    assert variant.name == "review-heavy"
    assert variant.directory == ".fabro/workflows/rh"


def test_workflow_toml_tolerates_a_namespace_without_a_repo_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-dispatch subparsers define no `--repo`; the probe must not raise."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    args = argparse.Namespace(workflow=None)
    assert not hasattr(args, "repo")

    assert workflow_toml(args=args) == _PLUGIN_ROOT.joinpath(*_WORKFLOW_SUBPATH)


def test_candidate_dispatcher_bin_resolves_from_plugin_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The canary bin anchors on the same plugin root (no `.claude-plugin` re-segment)."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("LIVESPEC_INSTALLED_PLUGIN_ROOT", raising=False)
    assert candidate_dispatcher_bin() == _PLUGIN_ROOT / "scripts" / "bin" / "dispatcher.py"


def test_candidate_dispatcher_bin_honors_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The canary bin honors CLAUDE_PLUGIN_ROOT in the flattened install cache."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert candidate_dispatcher_bin() == tmp_path / "scripts" / "bin" / "dispatcher.py"


def test_implement_and_review_prompts_enforce_scope_and_acceptance() -> None:
    """The shipped prompts carry the stage-consumption discipline."""
    implement_text = (_PROMPTS_DIR / "implement.md").read_text(encoding="utf-8")
    review_text = (_PROMPTS_DIR / "review.md").read_text(encoding="utf-8")

    assert "SCOPE-MINIMALISM" in implement_text
    assert "edit ONLY what the work-item requires" in implement_text
    assert "unrelated files, unrelated docs" in implement_text
    assert "acceptance criteria" in review_text
    assert "satisfies the work-item" in review_text
    assert "minimal scope" in review_text


def test_implement_prompt_leads_with_one_red_green_cycle_per_assertion() -> None:
    """The implementer reads the test-first loop before secondary guidance."""
    prompt = (_PROMPTS_DIR / "implement.md").read_text(encoding="utf-8")
    sections = [line for line in prompt.splitlines() if line.startswith("## ")]

    assert sections[0] == "## Test-first assertion loop — start here"
    ordered_steps = (
        "1. Pick exactly one acceptance assertion.",
        "2. Write one failing test for that assertion.",
        "3. Red-commit that test alone.",
        "4. While HEAD is that open Red, write the minimum product implementation",
        "5. Repeat from step 1 for the next assertion.",
    )
    positions = tuple(prompt.index(step) for step in ordered_steps)
    assert positions == tuple(sorted(positions))
    assert prompt.index(sections[0]) < prompt.index("### Refactoring for size")
    assert "One assertion gets one\n   observable Red-Green cycle." in prompt
    assert "in as few cohesive commits as the work naturally splits into" not in prompt
    assert "test+impl land atomically in one commit" not in prompt


def test_registered_workflow_prompts_use_the_single_injected_goal_and_stub_carveout() -> None:
    """Fabro's adapter-independent preamble owns the one complete goal copy.

    Fabro 0.254.0 prepends ``Goal: <graph goal>`` before dispatching any
    LLM-backed node, independently of whether that node's ACP adapter is
    Claude or Codex. A prompt-level goal template therefore creates the
    duplicate observed in production. Both registered workflow directories
    defer to that preamble, so changing an adapter cannot reintroduce it.
    """
    prompt_paths = tuple(
        path for directory in _REGISTERED_PROMPT_DIRS for path in sorted(directory.glob("*.md"))
    )

    assert len(prompt_paths) == 15
    for directory in _REGISTERED_PROMPT_DIRS:
        graph = (directory.parent / "workflow.fabro").read_text(encoding="utf-8")
        assert 'default_fidelity="full"' not in graph, directory
        assert 'fidelity="full"' not in graph, directory
    for path in prompt_paths:
        text = path.read_text(encoding="utf-8")
        assert "{{ goal }}" not in text, path
        assert _GOAL_PREAMBLE_REFERENCE in text, path

    implement = (_PROMPTS_DIR / "implement.md").read_text(encoding="utf-8")
    assert "no product file may be created or\nmodified before the first Red commit" in implement
    assert "every later product write\nrequires HEAD to be an open Red" in implement
    assert "The ONLY carveout is a new-module\nfailing stub" in implement
    assert "file that does not exist at HEAD" in implement
    assert "The stub must make that\nassertion FAIL; it must never satisfy it." in implement
    assert "Modifying an existing product\nfile outside an open Red" in implement


def test_dispatch_target_credential_wrapper_reads_configured_prefix(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"credential_wrapper": ["/opt/openbrain/with-openbrain-env.sh", "--"]}',
        encoding="utf-8",
    )

    assert read_dispatch_target_credential_wrapper(repo=tmp_path) == (
        "/opt/openbrain/with-openbrain-env.sh",
        "--",
    )
    assert "/opt/openbrain/with-openbrain-env.sh" in credential_wrapper_text(repo=tmp_path)


def test_dispatch_target_credential_wrapper_falls_back_for_missing_config(
    tmp_path: Path,
) -> None:
    assert read_dispatch_target_credential_wrapper(repo=tmp_path) == ()
    assert "no credential_wrapper configured" in credential_wrapper_text(repo=tmp_path)


@pytest.mark.parametrize(
    "config_text",
    [
        "{not-json",
        "[]",
        '{"credential_wrapper": "not-a-list"}',
        '{"credential_wrapper": ["/opt/openbrain/with-openbrain-env.sh", 42]}',
    ],
)
def test_dispatch_target_credential_wrapper_rejects_unusable_config_shapes(
    config_text: str,
    tmp_path: Path,
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(config_text, encoding="utf-8")

    assert read_dispatch_target_credential_wrapper(repo=tmp_path) == ()
    assert "no credential_wrapper configured" in credential_wrapper_text(repo=tmp_path)


def test_credential_gate_accepts_a_usable_live_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TEST_TOKEN)

    assert (
        check_credential_env(
            repo=tmp_path,
            probe=lambda *, token: _credential_status(token=token, usable=True),
        )
        is None
    )


def test_credential_gate_refuses_capacity_before_sandbox_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TEST_TOKEN)

    refusal = check_credential_env(
        repo=tmp_path,
        probe=lambda *, token: _credential_status(token=token, usable=False),
    )

    assert refusal is not None
    assert "refused before sandbox launch" in refusal
    assert "Observed condition: exhausted" in refusal
    assert "CLAUDE_CODE_OAUTH_TOKEN" in refusal
    assert "Wait before retrying" in refusal
    assert "GITHUB_APP_ID" in refusal
