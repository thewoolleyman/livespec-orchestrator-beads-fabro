"""The pre-dispatch proof-assets gate's own decisions, and what it projects.

Companion to `test_dispatcher_proof_release`, which covers the prerelease and the
rendering measurement. This module covers the GATE built on them: which items it
probes at all, the three-way split between a ready store, a refusal and an
UNOBSERVABLE forge, what it writes to the journal in each case, and the two
environment keys it projects into the sandbox.

WHY THE UNOBSERVABLE ARM GETS ITS OWN CASES. The clause requires a refusal when a
target lacks the prerelease, and this repository's own `verify_pr` breaker already
draws the line that makes that safe: "we could not look" must never be reported as
"it did not happen". An earlier draft of this gate collapsed the two and turned
every offline invocation into a refusal naming a tag whose absence nobody had
established -- 104 sealed tests among the casualties. So the discrimination is
asserted directly, in both directions, rather than left to the happy path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from inspect import signature
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_assets import (
    RENDERING_AUTHENTICATED_LINK,
    RENDERING_INLINE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    PROOF_ASSET_RENDERING_ENV_VAR,
    PROOF_ASSETS_RELEASE_TAG_ENV_VAR,
    PROOF_STORE_JOURNAL_STAGE,
    PUBLISH_BRANCH_ENV_VAR,
    ProofStoreUnobservable,
    proof_assets_refusal,
    proof_assets_refusal_for_items,
    proof_store_env_lines,
    publish_branch_for,
    repository_visibility,
    resolve_proof_store,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_release import (
    repository_visibility_from_view,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_PROOF_BEARING = """## Definition of Done

- The banner renders on the runs page.

References: ## Scenario 132 — A thing
"""

# A sentinel for "this fixture declares no tag at all", distinct from declaring
# `null` — the resolver treats those two differently and so must the fixture.
_UNSET = object()

_HUMAN_ONLY = """## Definition of Done

### Human-attested

Reason: the wording is a matter of taste no sandbox can grade.

- The banner's wording reads naturally.

References: ## Scenario 132 — A thing
"""


@dataclass(kw_only=True)
class _Runner:
    """A `CommandRunner` scripted per forge verb, recording every argv."""

    visibility: str = "PUBLIC"
    visibility_exit: int = 0
    view_exit: int = 0
    create_exit: int = 0
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
        if "repo" in argv:
            return CommandResult(
                exit_code=self.visibility_exit,
                stdout=json.dumps({"visibility": self.visibility}),
                stderr="",
            )
        if "create" in argv:
            return CommandResult(exit_code=self.create_exit, stdout="", stderr="gh refused")
        return CommandResult(exit_code=self.view_exit, stdout="{}", stderr="absent")


@dataclass(kw_only=True)
class _Journal:
    """Collects the records the gate appends."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _item(*, description: str, item_id: str = "bd-ib-b4u6b7") -> WorkItem:
    return WorkItem(
        id=item_id,
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


def _repo(*, tmp_path: Path, tag: object = _UNSET) -> Path:
    """A governed repository whose committed config optionally declares the tag.

    The `dispatcher` block is nested under the PLUGIN block, which is where
    `dispatcher_block` reads it from — a fixture that wrote `dispatcher` at the root
    would be silently ignored and every declared tag would read as the default,
    which is a fixture that cannot fail.
    """
    dispatcher: dict[str, object] = {} if tag is _UNSET else {"proof_assets_release_tag": tag}
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    return tmp_path


def test_the_publish_branch_is_derived_once_and_matches_the_plan_convention() -> None:
    """`feat/<work-item-id>`, from the one shared derivation.

    Asserted against the literal the plan builder also produces, because the whole
    value of a shared derivation is that the two agree — the `publish_draft` node
    pushes what this returns and the `pr` node readies the pull request on what the
    plan says.
    """
    assert publish_branch_for(work_item_id="bd-ib-b4u6b7") == "feat/bd-ib-b4u6b7"


def test_an_item_needing_no_captured_proof_never_touches_the_forge(tmp_path: Path) -> None:
    """The early return is asserted on the ABSENCE OF CALLS, not on the verdict.

    A gate that probed the forge and then returned None would produce the identical
    verdict while making a forge outage able to refuse a dispatch that needed
    nothing from the forge. The recorded argv list is the only instrument that can
    tell those two apart.
    """
    runner = _Runner()

    refusal = proof_assets_refusal(
        runner=runner,
        repo=_repo(tmp_path=tmp_path),
        item=_item(description=_HUMAN_ONLY),
        repository="owner/repo",
    )

    assert refusal is None
    assert runner.calls == []


def test_a_ready_store_journals_the_measurement_per_repository(tmp_path: Path) -> None:
    """The happy path: prerelease present, measurement journaled under its own stage."""
    runner = _Runner(visibility="PUBLIC", view_exit=0)
    journal = _Journal()

    refusal = proof_assets_refusal(
        runner=runner,
        repo=_repo(tmp_path=tmp_path),
        item=_item(description=_PROOF_BEARING),
        repository="owner/repo",
        journal=journal,
    )

    assert refusal is None
    assert len(journal.records) == 1
    record = journal.records[0]
    assert record["stage"] == PROOF_STORE_JOURNAL_STAGE
    assert record["work_item_id"] == "bd-ib-b4u6b7"
    assert record["repository"] == "owner/repo"
    assert record["rendering"] == RENDERING_INLINE
    assert record["inline_waived"] is False


def test_a_private_repository_journals_the_waiver(tmp_path: Path) -> None:
    """The control on the record above: the waiver tracks the measurement.

    Same gate, same fixture, one field different — so `inline_waived` is shown to be
    derived from what was measured rather than constant.
    """
    journal = _Journal()

    refusal = proof_assets_refusal(
        runner=_Runner(visibility="PRIVATE", view_exit=0),
        repo=_repo(tmp_path=tmp_path),
        item=_item(description=_PROOF_BEARING),
        repository="owner/private",
        journal=journal,
    )

    assert refusal is None
    assert journal.records[0]["rendering"] == RENDERING_AUTHENTICATED_LINK
    assert journal.records[0]["inline_waived"] is True


def test_an_unreachable_forge_is_journaled_as_unobservable_and_does_not_refuse(
    tmp_path: Path,
) -> None:
    """ "We could not look" is not "it is absent" — the whole point of the third arm.

    Both halves are asserted. The gate must NOT refuse, because nobody established
    the prerelease is missing; and it must SAY SO on the record, because a dispatch
    that proceeded without establishing its proof store should not look identical to
    one that established it.
    """
    journal = _Journal()

    refusal = proof_assets_refusal(
        runner=_Runner(visibility_exit=1),
        repo=_repo(tmp_path=tmp_path),
        item=_item(description=_PROOF_BEARING),
        repository="owner/repo",
        journal=journal,
    )

    assert refusal is None
    assert "unobservable" in journal.records[0]
    assert "could not be established" in str(journal.records[0]["unobservable"])


def test_an_answering_forge_with_no_prerelease_refuses_naming_the_tag(tmp_path: Path) -> None:
    """The ratified refusal, reachable ONLY when the forge answered.

    This is the discriminating pair for the case above: visibility reads fine, so
    the gate is entitled to conclude the prerelease is genuinely absent when its
    creation fails. Had the two arms been collapsed, this refusal and the
    unreachable-forge case would be indistinguishable.
    """
    refusal = proof_assets_refusal(
        runner=_Runner(visibility="PUBLIC", view_exit=1, create_exit=1),
        repo=_repo(tmp_path=tmp_path),
        item=_item(description=_PROOF_BEARING),
        repository="owner/repo",
    )

    assert refusal is not None
    assert "proof-assets" in refusal


def test_a_malformed_committed_tag_refuses_without_asking_the_forge(tmp_path: Path) -> None:
    """A configuration fault is caught before any network call.

    Asserted on the empty call list as well as the message: the key is unusable, so
    there is nothing to ask the forge about, and a gate that probed first would make
    a configuration error depend on connectivity.
    """
    runner = _Runner()

    resolution = resolve_proof_store(
        runner=runner,
        repo=_repo(tmp_path=tmp_path, tag=""),
    )

    assert isinstance(resolution, str)
    assert "dispatcher.proof_assets_release_tag" in resolution
    assert runner.calls == []


def test_the_unobservable_resolution_is_its_own_type(tmp_path: Path) -> None:
    """Not a `None` and not a refusal string, so a caller cannot conflate it."""
    resolution = resolve_proof_store(
        runner=_Runner(visibility_exit=1), repo=_repo(tmp_path=tmp_path)
    )

    assert isinstance(resolution, ProofStoreUnobservable)
    assert not isinstance(resolution, str)


def test_the_visibility_probe_reports_unmeasured_rather_than_raising(tmp_path: Path) -> None:
    """A non-zero probe and an unparseable payload both read as unmeasured."""
    assert repository_visibility(runner=_Runner(visibility_exit=1), repo=tmp_path) == ""
    assert repository_visibility(runner=_Runner(visibility="PUBLIC"), repo=tmp_path) == "PUBLIC"


def test_an_unparseable_or_keyless_visibility_payload_reads_as_unmeasured() -> None:
    """The reader tolerates every shape a forge might return.

    Three shapes, because each fails differently: not JSON at all, JSON that is not
    an object, and an object with no `visibility` key. All three must yield the
    unmeasured answer rather than raising inside a dispatch.
    """
    assert repository_visibility_from_view(stdout="not json at all") == ""
    assert repository_visibility_from_view(stdout="[1, 2]") == ""
    assert repository_visibility_from_view(stdout='{"other": "PUBLIC"}') == ""
    assert repository_visibility_from_view(stdout='{"visibility": 7}') == ""
    assert repository_visibility_from_view(stdout='{"visibility": "PUBLIC"}') == "PUBLIC"


def test_the_env_projection_is_pure_and_carries_the_branch_and_the_tag(tmp_path: Path) -> None:
    """Two keys, no forge call — the constraint that keeps the overlay offline-safe.

    The projection is reached from the run-config overlay, which every dispatch
    materializes and which the sealed test tier renders with no network. There is no
    runner to inject here BY DESIGN, and that is what this case documents.
    """
    lines = proof_store_env_lines(repo=_repo(tmp_path=tmp_path), work_item_id="bd-ib-b4u6b7")

    assert f'{PUBLISH_BRANCH_ENV_VAR} = "feat/bd-ib-b4u6b7"' in lines
    assert f'{PROOF_ASSETS_RELEASE_TAG_ENV_VAR} = "proof-assets"' in lines


def test_the_env_projection_omits_the_tag_when_the_committed_key_is_unusable(
    tmp_path: Path,
) -> None:
    """A malformed tag projects the BRANCH and withholds the tag.

    The branch is unconditional because `publish_draft` runs on every green janitor
    whatever the proof modes are; the tag is withheld because projecting a value
    nobody could validate would have the capture stage upload into a tag that does
    not exist and report the failure as its own.
    """
    lines = proof_store_env_lines(
        repo=_repo(tmp_path=tmp_path, tag=7),
        work_item_id="bd-ib-b4u6b7",
    )

    assert PUBLISH_BRANCH_ENV_VAR in lines
    assert PROOF_ASSETS_RELEASE_TAG_ENV_VAR not in lines


def test_the_env_projection_carries_the_measured_rendering_beside_the_branch_and_the_tag(
    tmp_path: Path,
) -> None:
    """All THREE keys, the rendering taken from the gate's OWN journal record.

    The record is written by the real plural gate through a real `JournalFile`
    rather than hand-authored JSONL, so "the rendering comes from the
    already-journaled per-repository measurement" is an OBSERVATION rather than a
    fixture claim: a projection that re-derived the measurement, or read some other
    field, would not find `inline` here.

    The signature assertion leads deliberately. The journal path is the whole seam
    — it is what lets a pure projection carry a measured value — and a behaviour
    assertion alone would report its absence as a `TypeError` rather than as the
    missing parameter it is.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    assert "journal_path" in signature(proof_store_env_lines).parameters

    refusal = proof_assets_refusal_for_items(
        runner=_Runner(visibility="PUBLIC", view_exit=0),
        repo=repo,
        items=[_item(description=_PROOF_BEARING)],
        journal=journal,
    )
    lines = proof_store_env_lines(repo=repo, work_item_id="bd-ib-b4u6b7", journal_path=journal.path)

    assert refusal is None
    assert f'{PUBLISH_BRANCH_ENV_VAR} = "feat/bd-ib-b4u6b7"' in lines
    assert f'{PROOF_ASSETS_RELEASE_TAG_ENV_VAR} = "proof-assets"' in lines
    assert f'{PROOF_ASSET_RENDERING_ENV_VAR} = "{RENDERING_INLINE}"' in lines


def test_a_private_repositorys_measured_waiver_is_projected_as_the_link_form(
    tmp_path: Path,
) -> None:
    """The control on the case above: the projected value TRACKS the measurement.

    Same gate, same projection, one visibility different. Without this the happy
    case is equally consistent with a projection that writes `inline` constantly,
    which is the one failure mode that could publish a reference nobody established
    was fetchable.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    refusal = proof_assets_refusal_for_items(
        runner=_Runner(visibility="PRIVATE", view_exit=0),
        repo=repo,
        items=[_item(description=_PROOF_BEARING)],
        journal=journal,
    )
    lines = proof_store_env_lines(repo=repo, work_item_id="bd-ib-b4u6b7", journal_path=journal.path)

    assert refusal is None
    assert f'{PROOF_ASSET_RENDERING_ENV_VAR} = "{RENDERING_AUTHENTICATED_LINK}"' in lines


def test_an_unobservable_forge_projects_no_rendering_key_at_all(tmp_path: Path) -> None:
    """The fail-safe: no measurement reached this run, so no value is invented.

    The gate journals an `unobservable` record carrying NO `rendering` field, and
    the projection must withhold the key rather than fill it in. Withholding it is
    what the capture prompt documents as its authenticated-link fallback, and it is
    the ONLY form that still lets a reader tell that fallback from a MEASURED
    waiver — the prompt asks the capture agent to say which one it took.

    Asserted beside the branch key, so this is "the rendering was withheld" rather
    than "the whole projection collapsed".
    """
    repo = _repo(tmp_path=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    refusal = proof_assets_refusal_for_items(
        runner=_Runner(visibility_exit=1),
        repo=repo,
        items=[_item(description=_PROOF_BEARING)],
        journal=journal,
    )
    lines = proof_store_env_lines(repo=repo, work_item_id="bd-ib-b4u6b7", journal_path=journal.path)

    assert refusal is None
    assert PUBLISH_BRANCH_ENV_VAR in lines
    assert PROOF_ASSET_RENDERING_ENV_VAR not in lines


def test_a_journal_with_no_store_record_projects_no_rendering_key(tmp_path: Path) -> None:
    """A journal the gate never wrote a store record to is the same fail-safe.

    Two shapes reach this, and both are ordinary rather than exceptional: a
    dispatch whose item carries no `factory_captured` assertion never probes the
    forge at all, and a journal holding only OTHER stages is what the readback sees
    before the gate has run. The unrelated record is present deliberately — a
    reader keying on position rather than on the store stage would pick it up.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": "bd-ib-b4u6b7"})

    lines = proof_store_env_lines(repo=repo, work_item_id="bd-ib-b4u6b7", journal_path=journal.path)

    assert PUBLISH_BRANCH_ENV_VAR in lines
    assert PROOF_ASSET_RENDERING_ENV_VAR not in lines


def test_a_declared_tag_is_projected_in_place_of_the_default(tmp_path: Path) -> None:
    """The control on the projection above: a repository's own tag reaches the sandbox."""
    lines = proof_store_env_lines(
        repo=_repo(tmp_path=tmp_path, tag="pod"),
        work_item_id="bd-ib-x",
    )

    assert f'{PROOF_ASSETS_RELEASE_TAG_ENV_VAR} = "pod"' in lines


def test_the_plural_gate_returns_the_first_refusal_and_stops(tmp_path: Path) -> None:
    """A repository-level fault is reported ONCE, not once per candidate.

    The prerelease is per repository, so every candidate would produce the same
    message; reporting N of them would read as N distinct faults. Asserted by
    passing two proof-bearing candidates and observing a single message.
    """
    refusal = proof_assets_refusal_for_items(
        runner=_Runner(visibility="PUBLIC", view_exit=1, create_exit=1),
        repo=_repo(tmp_path=tmp_path),
        items=[
            _item(description=_PROOF_BEARING, item_id="bd-ib-one"),
            _item(description=_PROOF_BEARING, item_id="bd-ib-two"),
        ],
    )

    assert refusal is not None
    assert refusal.count("proof-assets") == 1


def test_the_plural_gate_admits_a_selection_that_needs_no_store(tmp_path: Path) -> None:
    """The control: an all-human-attested selection passes and touches nothing."""
    runner = _Runner()

    refusal = proof_assets_refusal_for_items(
        runner=runner,
        repo=_repo(tmp_path=tmp_path),
        items=[_item(description=_HUMAN_ONLY)],
    )

    assert refusal is None
    assert runner.calls == []


def test_the_gate_without_a_journal_still_decides(tmp_path: Path) -> None:
    """The journal is optional, so the gate is callable where none exists.

    Asserted because the write goes through a duck-typed `append`: a gate that
    assumed a journal would raise on the callers that hold none, and the verdict
    must not depend on whether anyone is recording it.
    """
    refusal = proof_assets_refusal(
        runner=_Runner(visibility="PUBLIC", view_exit=0),
        repo=_repo(tmp_path=tmp_path),
        item=_item(description=_PROOF_BEARING),
        repository="owner/repo",
        journal=None,
    )

    assert refusal is None
