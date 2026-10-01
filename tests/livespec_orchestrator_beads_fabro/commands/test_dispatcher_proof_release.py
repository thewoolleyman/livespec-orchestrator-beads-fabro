"""The proof-assets prerelease, the measured image rendering, and their journal record.

Binds the `SPECIFICATION/contracts.md` Proof-of-Done-record clause ratified in
v114: the standing prerelease per governed repository whose tag is the committed
`dispatcher.proof_assets_release_tag`, the requirement that the Dispatcher create
it BEFORE the first dispatch of a repository whose item carries a
`factory_captured` assertion, the refusal NAMING THE TAG when a target lacks it
after that attempt, and the per-repository journaling of the rendering
measurement with its authenticated-link waiver.

WHY THE MEASUREMENT IS A DISPATCHER DETERMINATION AND NOT A COMMITTED LITERAL.
The clause requires the inline half to be MEASURED on a private repository before
a store is selected, and waived PER REPOSITORY when it cannot be met. A literal
baked in at implementation time would answer for one repository and be wrong for
the next one the fleet governs, and nothing would ever re-ask. So the
determination is made per dispatch, from the repository's own visibility, and
journaled -- which is also what makes the waiver auditable rather than implicit.

THE MEASUREMENT BEHIND THE POLICY, recorded here because the policy is only as
good as it is. Measured 2026-10-01 against live GitHub, read-only, with controls:
a PRIVATE repository's own-origin content returns 404 to an ANONYMOUS fetch
(`thewoolleyman/window-namer`, both `github.com/.../raw/...` and
`raw.githubusercontent.com`), while a PUBLIC repository's returns 200 through the
identical probe -- so the instrument could return the other answer. The forge
renders an inline image in a comment by fetching it through its own ANONYMOUS
image proxy, so an asset the anonymous fetch cannot reach cannot render inline.
That is why `private` resolves to the authenticated-link arm and why the waiver
exists at all.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_assets import (
    RENDERING_AUTHENTICATED_LINK,
    RENDERING_INLINE,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_release"
_SOURCE = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_proof_release.py"
)

_FACTORY_CAPTURED_DESCRIPTION = """## Definition of Done

- The banner renders on the runs page.

References: ## Scenario 132 — A thing
"""

_HUMAN_ATTESTED_ONLY_DESCRIPTION = """## Definition of Done

### Human-attested

Reason: the wording is a matter of taste no sandbox can grade.

- The banner's wording reads naturally.

References: ## Scenario 132 — A thing
"""


@dataclass(kw_only=True)
class _RecordingRunner:
    """A `CommandRunner` that replays scripted results and records every argv.

    Scripted on whether the argv CREATES rather than on call order, so a test can
    make the existence probe fail while the creation succeeds — which is the whole
    discrimination this module performs.
    """

    view_exit: int = 0
    create_exit: int = 0
    view_stdout: str = ""
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(list(argv))
        if "create" in argv:
            return CommandResult(exit_code=self.create_exit, stdout="", stderr="refused")
        return CommandResult(exit_code=self.view_exit, stdout=self.view_stdout, stderr="absent")


def _module() -> object:
    """The module under test, imported inside the body.

    Imported here rather than at module top so this slice's Red fails on a genuine
    assertion about the missing file rather than dying at COLLECTION with a
    `ModuleNotFoundError`, which would prove only unimportability.
    """
    return importlib.import_module(_MODULE)


def _item(*, description: str) -> WorkItem:
    return WorkItem(
        id="bd-ib-b4u6b7",
        type="task",
        status="ready",
        title="S5",
        description=description,
        origin="freeform",
        gap_id=None,
        rank="a3",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_the_module_exists_and_exports_the_prerelease_and_rendering_surface() -> None:
    """The names the dispatch path imports from this module."""
    assert _SOURCE.is_file(), f"{_SOURCE} does not exist"
    module = _module()

    for name in (
        "DEFAULT_PROOF_ASSETS_RELEASE_TAG",
        "PROOF_ASSETS_RELEASE_TAG_KEY",
        "ProofAssetsStoreResolution",
        "ensure_proof_assets_release",
        "item_is_proof_bearing",
        "proof_assets_release_tag",
        "proof_rendering_for_visibility",
        "proof_store_journal_record",
    ):
        assert hasattr(module, name), name


def test_the_tag_defaults_to_proof_assets_and_is_committed_configuration_only() -> None:
    """Absent key resolves the ratified default; a declared tag is honoured."""
    module = _module()

    assert module.proof_assets_release_tag(block={}) == "proof-assets"
    assert module.DEFAULT_PROOF_ASSETS_RELEASE_TAG == "proof-assets"
    assert module.proof_assets_release_tag(block={"proof_assets_release_tag": "pod"}) == "pod"


def test_a_malformed_tag_is_refused_naming_the_committed_key() -> None:
    """A blank or non-string tag refuses, and the message names the key to edit.

    Refused rather than defaulted: a target that WROTE the key meant to override
    the default, so silently sliding back onto `proof-assets` would store that
    repository's proof under a tag nobody declared.
    """
    module = _module()

    for bad in ("", "   ", 7, None):
        refusal = module.proof_assets_release_tag(block={"proof_assets_release_tag": bad})
        assert isinstance(refusal, str), bad
        assert "dispatcher.proof_assets_release_tag" in refusal


def test_an_item_with_a_factory_captured_assertion_is_proof_bearing() -> None:
    """Proof-bearing is a property of the item's Definition of Done, not of its type.

    The human-attested-only control is what makes this discriminating: that item
    HAS a Definition of Done and HAS assertions, so a predicate keyed on the
    section's presence would call it proof-bearing and provision a prerelease for
    a repository that will never store an asset.
    """
    module = _module()

    assert module.item_is_proof_bearing(item=_item(description=_FACTORY_CAPTURED_DESCRIPTION))
    assert not module.item_is_proof_bearing(
        item=_item(description=_HUMAN_ATTESTED_ONLY_DESCRIPTION)
    )
    assert not module.item_is_proof_bearing(item=_item(description="no section at all"))


def test_a_private_repository_waives_the_inline_half_and_a_public_one_does_not() -> None:
    """The measured policy, asserted in both directions.

    Both arms matter and neither is the safe default. Resolving `inline` for a
    private repository renders a permanently broken image where the proof should
    be; resolving `authenticated_link` for a public one needlessly withholds the
    inline rendering the clause prefers.
    """
    module = _module()

    assert module.proof_rendering_for_visibility(visibility="PRIVATE") == (
        RENDERING_AUTHENTICATED_LINK
    )
    assert module.proof_rendering_for_visibility(visibility="private") == (
        RENDERING_AUTHENTICATED_LINK
    )
    assert module.proof_rendering_for_visibility(visibility="PUBLIC") == RENDERING_INLINE


def test_an_unknown_visibility_waives_the_inline_half_rather_than_guessing() -> None:
    """The fail-safe direction is the WAIVER, and that choice is deliberate.

    An unreadable visibility means the measurement did not happen. Of the two
    answers, the waiver costs an inline rendering the repository might have
    supported, while the other risks publishing an asset reference that leaks on a
    repository nobody established was public. The proof itself is never waived in
    either arm, so the waiver is the cheap mistake.
    """
    module = _module()

    assert module.proof_rendering_for_visibility(visibility="") == RENDERING_AUTHENTICATED_LINK
    assert (
        module.proof_rendering_for_visibility(visibility="INTERNAL") == RENDERING_AUTHENTICATED_LINK
    )


def test_an_existing_prerelease_is_not_recreated(tmp_path: Path) -> None:
    """Idempotence: when the probe finds the tag, no creation is attempted.

    Asserted on the RECORDED ARGVS rather than on the returned resolution, because
    a module that created the release every dispatch would return an identical
    resolution while rewriting a release the clause says must not be disturbed
    while any record references it.
    """
    module = _module()
    runner = _RecordingRunner(view_exit=0, view_stdout='{"tagName": "proof-assets"}')

    resolution = module.ensure_proof_assets_release(
        runner=runner, repo=tmp_path, tag="proof-assets", visibility="PUBLIC"
    )

    assert not isinstance(resolution, str), resolution
    assert resolution.created is False
    assert not any("create" in argv for argv in runner.calls)


def test_an_absent_prerelease_is_created_as_a_prerelease(tmp_path: Path) -> None:
    """The creation argv marks it a PRERELEASE, so it is never the latest release.

    The `--prerelease` flag is the load-bearing part rather than a detail: the
    clause requires the release to be marked prerelease precisely so a proof-asset
    carrier never becomes the repository's advertised latest release.
    """
    module = _module()
    runner = _RecordingRunner(view_exit=1, create_exit=0)

    resolution = module.ensure_proof_assets_release(
        runner=runner, repo=tmp_path, tag="proof-assets", visibility="PRIVATE"
    )

    assert not isinstance(resolution, str), resolution
    assert resolution.created is True
    create = next(argv for argv in runner.calls if "create" in argv)
    assert create[:3] == ["gh", "release", "create"]
    assert "proof-assets" in create
    assert "--prerelease" in create


def test_a_creation_that_fails_refuses_naming_the_tag(tmp_path: Path) -> None:
    """A target still lacking the tag after the attempt refuses before any run.

    The tag has to be IN the message: the remedy is to create that release, and a
    refusal that named only the repository would leave an operator guessing which
    tag the factory wanted.
    """
    module = _module()
    runner = _RecordingRunner(view_exit=1, create_exit=1)

    refusal = module.ensure_proof_assets_release(
        runner=runner, repo=tmp_path, tag="pod-assets", visibility="PUBLIC"
    )

    assert isinstance(refusal, str)
    assert "pod-assets" in refusal


def test_the_resolution_carries_a_store_bound_to_the_measured_rendering(tmp_path: Path) -> None:
    """The store the capture stage uses is built HERE, once, from the measurement.

    This is the resolve-once-project-everywhere discipline: the capture stage
    receives a store already bound to the measured rendering, so no seam
    downstream re-derives whether this repository waives the inline half.
    """
    module = _module()
    runner = _RecordingRunner(view_exit=0, view_stdout="{}")

    resolution = module.ensure_proof_assets_release(
        runner=runner, repo=tmp_path, tag="proof-assets", visibility="PRIVATE"
    )

    assert not isinstance(resolution, str), resolution
    assert resolution.store.release_tag == "proof-assets"
    assert resolution.store.rendering == RENDERING_AUTHENTICATED_LINK
    assert resolution.rendering == RENDERING_AUTHENTICATED_LINK


def test_the_journal_record_names_the_repository_the_store_and_the_waiver() -> None:
    """The waiver is journaled PER REPOSITORY, naming the store measured.

    All four facts are asserted because the clause requires each: which repository
    was measured, which store, what the measurement found, and whether the inline
    half is waived. A record missing the store name could not answer "which store
    was measured" when a second store is added.
    """
    module = _module()

    record = module.proof_store_journal_record(
        repository="thewoolleyman/livespec-orchestrator-beads-fabro",
        tag="proof-assets",
        visibility="PRIVATE",
        rendering=RENDERING_AUTHENTICATED_LINK,
        created=True,
    )

    assert record["repository"] == "thewoolleyman/livespec-orchestrator-beads-fabro"
    assert record["store"] == "release_assets"
    assert record["proof_assets_release_tag"] == "proof-assets"
    assert record["visibility"] == "PRIVATE"
    assert record["rendering"] == RENDERING_AUTHENTICATED_LINK
    assert record["inline_waived"] is True
    assert record["prerelease_created"] is True


def test_the_journal_record_reports_no_waiver_when_the_forge_renders_inline() -> None:
    """The control on the record above: `inline_waived` tracks the measurement.

    Without this leg, `inline_waived is True` would pass equally well against a
    record that hardcoded it — and a journal that always reports a waiver tells a
    reader nothing about the repository it was written for.
    """
    module = _module()

    record = module.proof_store_journal_record(
        repository="owner/public",
        tag="proof-assets",
        visibility="PUBLIC",
        rendering=RENDERING_INLINE,
        created=False,
    )

    assert record["inline_waived"] is False
    assert record["prerelease_created"] is False
