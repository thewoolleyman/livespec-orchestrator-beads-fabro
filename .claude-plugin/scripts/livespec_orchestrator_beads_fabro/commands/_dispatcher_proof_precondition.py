"""The pre-dispatch proof-assets gate, and the store projection the sandbox reads.

`SPECIFICATION/contracts.md`'s Proof-of-Done-record clause (ratified v114)
requires the standing proof-assets prerelease to be created by the Dispatcher
BEFORE the first dispatch of a repository whose item carries a `factory_captured`
assertion, and requires a dispatch whose target lacks it after that attempt to
refuse BEFORE any run exists. This module is the gate that does both, plus the
projection that carries the resolved store into the sandbox.

WHY THE GATE SITS IN THE PRE-DISPATCH WALL. "Before any run exists" is a
positional requirement, not a wish: the wall runs after target selection and
before admission, so a refused item is never claimed and there is no Fabro run to
reap. That is the same position the acceptance-criteria wall already occupies, and
putting this beside it is what makes both refusals reachable through the single
`dispatch` and `loop` entry points rather than through a third path.

WHY THE SANDBOX RECEIVES VALUES AND NEVER RESOLVES. The capture stage needs three
facts: which branch its draft pull request rides, which release tag to upload to,
and whether this repository's record references images inline or by authenticated
link. All three are resolved HOST-side and projected as environment variables,
because the third is a per-repository MEASUREMENT and a sandbox that re-derived it
would waive the inline half on repositories that support it. The capture prompt
refuses rather than guessing when a value is absent, which is why no default is
projected.

WHY THE PUBLISH BRANCH RIDES THE ENVIRONMENT RATHER THAN A WORKFLOW INPUT. The
`publish_draft` node is a COMMAND node, so it cannot read the rendered goal the
way the `pr` prompt does, and `CONTRACT_INPUT_NAMES` is a CLOSED set carrying no
publish-branch name. The run-config overlay's environment table is the existing
seam for exactly this -- it already carries `LIVESPEC_GIT_AUTHOR_NAME` for the
`needs_human` node's emergency commit -- so the branch rides there too.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_assets import PROOF_RENDERINGS
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_release import (
    ProofAssetsStoreResolution,
    ensure_proof_assets_release,
    item_is_proof_bearing,
    proof_assets_release_tag,
    proof_assets_release_tag_refusal,
    proof_store_journal_record,
    repository_visibility_from_view,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PROOF_ASSETS_RELEASE_TAG_ENV_VAR",
    "PROOF_ASSET_RENDERING_ENV_VAR",
    "PROOF_STORE_JOURNAL_STAGE",
    "PUBLISH_BRANCH_ENV_VAR",
    "ProofStoreUnobservable",
    "proof_assets_refusal",
    "proof_assets_refusal_for_items",
    "proof_store_env_lines",
    "publish_branch_for",
    "repository_visibility",
    "resolve_proof_store",
]

# The three names the sandbox reads. `LIVESPEC_`-prefixed like every other
# non-secret key the overlay projects, so a reader of the sandbox environment can
# tell a factory-supplied value from the image's own.
PUBLISH_BRANCH_ENV_VAR = "LIVESPEC_PUBLISH_BRANCH"
PROOF_ASSETS_RELEASE_TAG_ENV_VAR = "LIVESPEC_PROOF_ASSETS_RELEASE_TAG"
PROOF_ASSET_RENDERING_ENV_VAR = "LIVESPEC_PROOF_ASSET_RENDERING"

# The journal stage the per-repository store record is written under.
PROOF_STORE_JOURNAL_STAGE = "proof-asset-store"

_VISIBILITY_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class ProofStoreUnobservable:
    """The forge could not be ASKED whether the standing prerelease exists.

    A distinct type rather than a `None` or a refusal string, so a caller cannot
    accidentally treat "unobservable" as "absent". `detail` is journaled, because a
    dispatch that proceeded without establishing its proof store should say so on
    the record rather than look identical to one that established it.
    """

    detail: str


def publish_branch_for(*, work_item_id: str) -> str:
    """The publish branch one work-item's run publishes under.

    The ONE derivation of this name. `build_plan` hangs it on the plan for the
    seams that read the plan, and the run-config overlay calls this directly
    because it is reached from a path that is already at its file-size ceiling and
    cannot take another threaded argument. Two CALL SITES of one function is the
    resolve-once discipline; two spellings of `feat/<id>` would not be.
    """
    return f"feat/{work_item_id}"


def repository_visibility(*, runner: CommandRunner, repo: Path) -> str:
    """Probe the governed repository's visibility, or return the empty string.

    The empty string means UNMEASURED, which the rendering resolver treats as a
    reason to waive the inline half rather than as a reason to guess. A forge that
    could not answer is not a bug in this package, and the fail-safe answer is
    already defined.
    """
    result = runner.run(
        argv=["gh", "repo", "view", "--json", "visibility"],
        cwd=repo,
        timeout_seconds=_VISIBILITY_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return ""
    return repository_visibility_from_view(stdout=result.stdout)


def resolve_proof_store(
    *, runner: CommandRunner, repo: Path
) -> ProofAssetsStoreResolution | ProofStoreUnobservable | str:
    """Resolve this repository's proof asset store, creating the prerelease if absent.

    THREE outcomes, and the third is the one that matters most. A resolution means
    the store is ready. A `str` is a refusal -- the committed key is malformed, or
    the forge ANSWERED and the prerelease is absent and could not be created.
    `ProofStoreUnobservable` means the forge could not be ASKED at all, which is a
    different fact and must not be reported as the second.

    That distinction is this repository's own standing rule, not a new one: the
    `verify_pr` breaker draws exactly the same line between
    `LIVESPEC_PR_NOT_CREATED` and `LIVESPEC_PR_NOT_CREATED_CHECK_FAILED`, because
    "we could not look" must never be reported as "the publish did not happen".
    Collapsing them here would turn every offline or unauthenticated invocation --
    the whole hermetic test tier among them -- into a refusal naming a tag whose
    absence nobody established.

    The VISIBILITY probe is the discriminator, and it is one this function already
    had to make. A repository whose visibility cannot be read is one whose forge is
    not answering; a repository whose visibility reads fine and whose prerelease
    still cannot be created genuinely lacks it.
    """
    block = dispatcher_block(cwd=repo)
    refusal = proof_assets_release_tag_refusal(block=block)
    if refusal is not None:
        return refusal
    visibility = repository_visibility(runner=runner, repo=repo)
    if not visibility:
        return ProofStoreUnobservable(
            detail=(
                "the forge did not answer `gh repo view --json visibility` for this "
                "repository, so whether the standing proof-assets prerelease exists "
                "could not be established; proceeding without refusing, because an "
                "unobservable store is not an absent one"
            )
        )
    return ensure_proof_assets_release(
        runner=runner, repo=repo, tag=proof_assets_release_tag(block=block), visibility=visibility
    )


def proof_assets_refusal(
    *,
    runner: CommandRunner,
    repo: Path,
    item: WorkItem,
    repository: str,
    journal: object = None,
) -> str | None:
    """The pre-dispatch gate: None to proceed, or the refusal text.

    An item carrying NO `factory_captured` assertion returns None without probing
    the forge at all. That early return is deliberate rather than an optimization:
    provisioning a release for a repository whose item will never store an asset
    would make a forge outage refuse a dispatch that needed nothing from the forge.

    When the item IS proof-bearing, the resolution is journaled PER REPOSITORY --
    naming the store measured, what the measurement found, and whether the inline
    half is waived for it -- which is the clause's own requirement and what makes
    the waiver auditable instead of implicit.
    """
    if not item_is_proof_bearing(item=item):
        return None
    resolution = resolve_proof_store(runner=runner, repo=repo)
    if isinstance(resolution, str):
        return resolution
    if isinstance(resolution, ProofStoreUnobservable):
        _append_store_record(
            journal=journal,
            work_item_id=item.id,
            record={"repository": repository, "unobservable": resolution.detail},
        )
        return None
    _append_store_record(
        journal=journal,
        work_item_id=item.id,
        record=proof_store_journal_record(
            repository=repository,
            tag=resolution.store.release_tag,
            visibility=resolution.visibility,
            rendering=resolution.rendering,
            created=resolution.created,
        ),
    )
    return None


def proof_store_env_lines(
    *, repo: Path, work_item_id: str, journal_path: Path | None = None
) -> str:
    """The overlay env lines the publish and capture stages read.

    PURE BY CONSTRUCTION -- it reads the committed configuration, derives a branch
    name, and reads back a measurement somebody else already took. It performs NO
    forge call. That constraint is not stylistic. This function is reached from the
    run-config overlay, which every dispatch materializes and which the hermetic
    test tier exercises without a network; an earlier draft probed the forge here
    and spawned a real `gh` in 104 otherwise sealed tests. A projection that cannot
    be rendered offline does not belong on this path.

    Two of the three keys are facts about the repository that need nobody's
    permission to state -- the publish branch, derived from the item id through the
    one shared derivation, and the release tag, read from the repository's own
    committed configuration.

    THE THIRD KEY IS THE MEASURED RENDERING, AND IT ARRIVES BY READBACK rather than
    by measurement. `proof_assets_refusal` has already probed this repository's
    visibility at the pre-dispatch gate and journaled the resolution under
    `PROOF_STORE_JOURNAL_STAGE`, so the value exists before this projection runs
    and the only honest thing left to do is read it. That is what reconciles the
    purity constraint above with the clause's requirement: the clause waives the
    inline half only where no API-drivable store satisfies it, so a projection that
    could not carry a measured `inline` would waive it on the public repositories
    the measured release-assets store does satisfy.

    `journal_path` is threaded in rather than derived, because the journal location
    is an INVOCATION fact (`--journal` overrides it) and a second derivation could
    not be proven to agree with the first. A caller that holds none -- and a
    dispatch whose freshest record for this repository could not measure -- projects
    NO rendering key at all, which is what the capture prompt documents as its
    fail-safe: an absent value means no measurement reached this run, the prompt
    takes the AUTHENTICATED-LINK form and says that it did so, and a reader can
    still tell that fallback from a measured waiver. Projecting
    `authenticated_link` for an unmeasured repository would destroy exactly that
    distinction while buying nothing.
    """
    tag = proof_assets_release_tag(block=dispatcher_block(cwd=repo))
    lines = (
        f"{PUBLISH_BRANCH_ENV_VAR} = "
        f"{json.dumps(publish_branch_for(work_item_id=work_item_id))}\n"
    )
    rendering = _journaled_rendering(journal_path=journal_path)
    if rendering:
        lines += f"{PROOF_ASSET_RENDERING_ENV_VAR} = {json.dumps(rendering)}\n"
    if proof_assets_release_tag_refusal(block=dispatcher_block(cwd=repo)) is not None:
        return lines
    return lines + f"{PROOF_ASSETS_RELEASE_TAG_ENV_VAR} = {json.dumps(tag)}\n"


def _journaled_rendering(*, journal_path: Path | None) -> str:
    """The rendering the gate already measured, or the empty string.

    NEWEST-WINS, and the scan stops at the first store record it finds rather than
    searching past it for one carrying a usable rendering. The difference matters in
    exactly the case that is easy to get wrong: a dispatch whose gate found the
    forge UNOBSERVABLE journals a record with no `rendering` field, and skipping
    past it to an older measurement would project a visibility nobody established
    THIS time while looking indistinguishable from a fresh reading.

    Every tolerance here fails SAFE onto the empty string -- no journal, no store
    record, a record whose `rendering` is absent, not a string, or outside the
    closed pair -- because the empty string projects no key, and no key is the
    capture prompt's authenticated-link fallback. The closed-pair check is
    deliberate rather than defensive: a value the prompt does not understand would
    otherwise reach the sandbox as an instruction nothing acts on.
    """
    if journal_path is None:
        return ""
    for record in reversed(read_journal_records(journal_path=journal_path)):
        if record.get("stage") != PROOF_STORE_JOURNAL_STAGE:
            continue
        rendering = record.get("rendering")
        if isinstance(rendering, str) and rendering in PROOF_RENDERINGS:
            return rendering
        return ""
    return ""


def _append_store_record(*, journal: object, work_item_id: str, record: dict[str, object]) -> None:
    """Write the store record to the journal when one was supplied.

    The journal is optional so the gate is callable from a hermetic test and from
    a caller that holds none, and the write goes through the journal's own
    `append` rather than a second serializer.
    """
    append = getattr(journal, "append", None)
    if append is None:
        return
    append(
        record={
            "stage": PROOF_STORE_JOURNAL_STAGE,
            "work_item_id": work_item_id,
            **record,
        }
    )


def proof_assets_refusal_for_items(
    *,
    runner: CommandRunner,
    repo: Path,
    items: Sequence[WorkItem],
    journal: object = None,
) -> str | None:
    """The gate over a whole selection: the FIRST refusal, or None.

    The drain selects several candidates at once, and this returns on the first
    refusal rather than enumerating every one. That is the conservative shape: the
    refusal is a REPOSITORY-level fact -- the prerelease is per repository, not per
    item -- so a second candidate would produce the same message, and reporting it
    N times would read as N distinct faults.

    `repository` is the governed repository's directory name. The journal it is
    written to is that repository's own, so the name disambiguates a record read
    out of context without a forge round-trip to resolve `owner/name`.
    """
    for item in items:
        refusal = proof_assets_refusal(
            runner=runner, repo=repo, item=item, repository=repo.name, journal=journal
        )
        if refusal is not None:
            return refusal
    return None
