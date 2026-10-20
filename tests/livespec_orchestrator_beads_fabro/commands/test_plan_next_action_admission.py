"""The repository identity a plan pointer's required result names, at write time.

The typed `next_action` writer graded a `required_result`'s `repo` field as any
non-empty string, while the shared authoritative result reader resolves only the
identities `_plan_result_repository` enumerates. So a value the writer ACCEPTED
could be one the reader can never resolve, and every later observation of it read
`unobservable` from repository resolution — which `resume_directive` answers by
withholding dispatch until the budget deadline, while a correction is refused by
design because the obligation it would replace is itself unobservable. One
malformed field therefore locked the obligation for its whole budget, measured
2026-10-18 on plan epic `bd-ib-6tcjfx`, whose pointer named the project's own
repository in the full `owner/name` form.

EVERY CASE DRIVES A PUBLIC WRITER — `set_next_action` — rather than the admission
in isolation, because the defect was a DISAGREEMENT between a writer and a reader
and only the writer's own path establishes which side this repository takes. The
accepted-result case then reads the obligation back through `resume_directive`,
the surface whose withheld dispatch was the measured cost.

THE POSITIVE CONTROL IS LOAD-BEARING. A writer that refused every repository
identity would satisfy every refusal case here, so the project's own bare
directory name is written into the same tenant and asserted both ACCEPTED and
OBSERVED through the ledger.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    chain_cache_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.commands._plan_handoff import append_handoff
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NextAction,
    ResumeDirective,
    resume_directive,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action_validation import (
    NextActionRefusal,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNSATISFIED,
    SOURCE_LEDGER,
    SOURCE_REPOSITORY_RESOLUTION,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
# The project's own repository written as a forge path. It is the exact shape the
# measured incident carried, and the reader resolves a BARE repository name, so
# this identity is unresolvable however correct it looks to its author.
_OWNER_PATH = f"thewoolleyman/{_PROJECT_NAME}"
_CONTROL_EPIC = "bd-ib-admitcontrol"
_CONTROL_TARGET = "bd-ib-admitcontroltarget"
_PATH_EPIC = "bd-ib-admitpath"
_PATH_TARGET = "bd-ib-admitpathtarget"
_UNKNOWN_EPIC = "bd-ib-admitunknown"
_UNKNOWN_TARGET = "bd-ib-admitunknowntarget"
_HANDOFF_EPIC = "bd-ib-admithandoff"
_HANDOFF_TARGET = "bd-ib-admithandofftarget"
_SUGGEST_EPIC = "bd-ib-admitsuggest"
_SUGGEST_TARGET = "bd-ib-admitsuggesttarget"
_FOREIGN_PATH_EPIC = "bd-ib-admitforeign"
_FOREIGN_PATH_TARGET = "bd-ib-admitforeigntarget"
_BARE_EPIC = "bd-ib-admitbare"
_BARE_TARGET = "bd-ib-admitbaretarget"
# A repository identity carrying no path separator at all, so its refusal cannot
# be satisfied by anything this project's own spellings happen to share.
_UNKNOWN_REPO = "a-repository-this-host-has-never-cloned"
# The same unresolvable name written as a forge path. Its LAST SEGMENT does not
# resolve either, which is what makes it the control for a bare-name suggestion
# that is COMPUTED rather than pasted out of the identity it was handed.
_FOREIGN_PATH = f"thewoolleyman/{_UNKNOWN_REPO}"
# The phrase a refusal uses to name a bare identity that WOULD resolve. The bare
# project name is a substring of its own forge path, so the assertion keys on
# this phrase and the quoted identity rather than on the name alone.
_SUGGESTION = "resolves as"
_SESSION = "claude:plan-admission"
_NOW = "2026-10-18T18:30:00Z"
# Far enough ahead that the resume's own real-clock expiry reading can never
# reach it, so a withheld dispatch here is never an expired budget.
_FAR_FUTURE = "2099-01-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _hermetic_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _fake(*, config: StoreConfig) -> FakeBeadsClient:
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    return client


def _project(*, tmp_path: Path) -> StoreConfig:
    repo = tmp_path / _PROJECT_NAME
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return store_config(repo=repo)


def _seed_epic(*, config: StoreConfig, epic_id: str, target_id: str) -> None:
    """One plan epic carrying an authority chain, plus the item its result names."""
    fake = _fake(config=config)
    for issue_id, status in ((epic_id, "active"), (target_id, "ready")):
        _ = fake.create_issue(
            draft=IssueDraft(
                issue_id=issue_id,
                issue_type="epic" if issue_id == epic_id else "feature",
                title=issue_id,
                description="Definition of Done\n\n- A thing holds.",
                assignee=None,
                created_at="2026-10-18T08:00:00Z",
                metadata={"rank": "a0"},
            )
        )
        fake.update_issue(issue_id=issue_id, status=status)
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=epic_id,
        metadata=chain_cache_metadata(
            existing_metadata={"rank": "a0"},
            latest_closed=None,
            current=genesis,
        ),
    )


def _action(*, target_id: str, repo: str) -> NextAction:
    return NextAction(
        kind="impl",
        ref=target_id,
        text="Keep driving the slice.",
        required_result={"repo": repo, "item_status": {"item_id": target_id, "status": "done"}},
        budget={"deadline": _FAR_FUTURE, "max_handoffs": 5},
    )


def _epic_state(*, config: StoreConfig, epic_id: str) -> tuple[object, int]:
    """Everything a refused write must have left untouched on one epic.

    The metadata carries the pointer AND the authority chain's own cache, so a
    refusal that had already committed its transition shows up here even though
    the pointer it would have projected was never written; the comment count is
    what a prematurely appended handoff or progress event moves.
    """
    client = _fake(config=config)
    record = client.show_issue(issue_id=epic_id)
    return record.get("metadata"), len(client.list_comments(issue_id=epic_id))


def _write_and_resume(
    *,
    config: StoreConfig,
    epic_id: str,
    target_id: str,
    repo: str,
) -> tuple[NextActionRefusal | None, ResumeDirective]:
    _seed_epic(config=config, epic_id=epic_id, target_id=target_id)
    refusal = set_next_action(
        config=config,
        epic_id=epic_id,
        action=_action(target_id=target_id, repo=repo),
        session=_SESSION,
        now=_NOW,
    )
    return refusal, resume_directive(config=config, epic_id=epic_id, unattended=True)


def test_a_required_result_the_writer_accepts_is_read_as_observed(tmp_path: Path) -> None:
    """Every accepted pointer is read as satisfied or unsatisfied, never unresolvable.

    The two writes go into ONE tenant and differ only in the repository identity
    their required result names. The control names the project's own directory
    name and must be accepted AND observed; the candidate names the same
    repository as a forge path, which the reader cannot resolve — so the writer
    must not accept it, because an accepted-then-unobservable obligation is
    exactly the state that locks a plan for its whole budget.
    """
    config = _project(tmp_path=tmp_path)
    control = _write_and_resume(
        config=config,
        epic_id=_CONTROL_EPIC,
        target_id=_CONTROL_TARGET,
        repo=_PROJECT_NAME,
    )
    candidate = _write_and_resume(
        config=config,
        epic_id=_PATH_EPIC,
        target_id=_PATH_TARGET,
        repo=_OWNER_PATH,
    )

    for refusal, directive in (control, candidate):
        if refusal is not None:
            continue
        findings = "\n".join(directive.findings)
        assert f"source={SOURCE_REPOSITORY_RESOLUTION}" not in findings, findings
        assert directive.observation is not None, directive
        assert directive.observation.status in (
            OBSERVATION_SATISFIED,
            OBSERVATION_UNSATISFIED,
        ), directive.observation
    control_refusal, control_directive = control
    assert control_refusal is None, control_refusal
    assert control_directive.observation is not None, control_directive
    assert control_directive.observation.status == OBSERVATION_UNSATISFIED
    assert control_directive.observation.source == SOURCE_LEDGER


def test_an_unresolvable_repository_is_refused_naming_the_identity(tmp_path: Path) -> None:
    """The refusal names the identity it could not resolve, and writes nothing.

    The identity is the ONE field its author has to change, so a refusal that
    withheld it would send them to read the resolver rather than fix the value —
    and the `repo` field is not echoed anywhere else in a refused write.

    THE BEFORE-AND-AFTER STATE IS THE SECOND HALF, and it is a different claim:
    the refusal is owed BEFORE any ledger write, and a writer that refused after
    appending its handoff or committing its epoch transition would return this
    very same refusal while having spent a handoff unit on it.
    """
    config = _project(tmp_path=tmp_path)
    _seed_epic(config=config, epic_id=_UNKNOWN_EPIC, target_id=_UNKNOWN_TARGET)
    _seed_epic(config=config, epic_id=_HANDOFF_EPIC, target_id=_HANDOFF_TARGET)
    pointer_before = _epic_state(config=config, epic_id=_UNKNOWN_EPIC)
    handoff_before = _epic_state(config=config, epic_id=_HANDOFF_EPIC)

    pointer_refusal = set_next_action(
        config=config,
        epic_id=_UNKNOWN_EPIC,
        action=_action(target_id=_UNKNOWN_TARGET, repo=_UNKNOWN_REPO),
        session=_SESSION,
        now=_NOW,
    )
    handoff_refusal = append_handoff(
        config=config,
        epic_id=_HANDOFF_EPIC,
        body="Handing the slice over.",
        author=_SESSION,
        now=_NOW,
        next_action=_action(target_id=_HANDOFF_TARGET, repo=_UNKNOWN_REPO),
    )

    for refusal in (pointer_refusal, handoff_refusal):
        assert isinstance(refusal, NextActionRefusal), refusal
        assert _UNKNOWN_REPO in refusal.detail, refusal.detail
    assert _epic_state(config=config, epic_id=_UNKNOWN_EPIC) == pointer_before
    assert _epic_state(config=config, epic_id=_HANDOFF_EPIC) == handoff_before


def test_an_absolute_repository_identity_is_refused_with_the_canonical_bare_name(
    tmp_path: Path,
) -> None:
    """A new pointer must name its repository with the canonical bare identity."""
    config = _project(tmp_path=tmp_path)
    _seed_epic(config=config, epic_id=_PATH_EPIC, target_id=_PATH_TARGET)

    refusal = set_next_action(
        config=config,
        epic_id=_PATH_EPIC,
        action=_action(target_id=_PATH_TARGET, repo=str(config.repo_root)),
        session=_SESSION,
        now=_NOW,
    )

    assert isinstance(refusal, NextActionRefusal), refusal
    assert "canonical bare repository identity" in refusal.detail
    assert _PROJECT_NAME in refusal.detail


def test_the_forge_path_form_of_this_project_is_refused_naming_the_bare_identity(
    tmp_path: Path,
) -> None:
    """A path-form identity whose last segment resolves is refused with that segment.

    This is the measured incident's own shape, and the author who wrote it had
    no way to see what was wrong: `thewoolleyman/<repo>` is the project's real
    forge path, so a refusal that only reported the value back reads as a
    refusal of the correct answer. Naming the identity that WOULD resolve is
    what makes the one-character fix visible.

    THE REFUSAL IS NEVER A NORMALIZATION. Stripping the owner would make
    `<any-owner>/<this-repo-name>` resolve to THIS checkout, which is the one
    thing the reader's own origin-name resolution refuses to do, so a wrong
    owner would have its result read as this project's and reported satisfied.

    THE TWO CONTROLS ARE WHAT MAKE THE SUGGESTION MEAN ANYTHING. A path whose
    last segment does NOT resolve, and an identity carrying no separator at all,
    must each be refused with NO suggestion — otherwise a refusal that simply
    pasted a fragment of whatever it was handed would satisfy the case above.
    """
    config = _project(tmp_path=tmp_path)
    for epic_id, target_id in (
        (_SUGGEST_EPIC, _SUGGEST_TARGET),
        (_FOREIGN_PATH_EPIC, _FOREIGN_PATH_TARGET),
        (_BARE_EPIC, _BARE_TARGET),
    ):
        _seed_epic(config=config, epic_id=epic_id, target_id=target_id)

    def _refuse(*, epic_id: str, target_id: str, repo: str) -> NextActionRefusal:
        refusal = set_next_action(
            config=config,
            epic_id=epic_id,
            action=_action(target_id=target_id, repo=repo),
            session=_SESSION,
            now=_NOW,
        )
        assert isinstance(refusal, NextActionRefusal), refusal
        return refusal

    suggested = _refuse(epic_id=_SUGGEST_EPIC, target_id=_SUGGEST_TARGET, repo=_OWNER_PATH)
    foreign = _refuse(
        epic_id=_FOREIGN_PATH_EPIC, target_id=_FOREIGN_PATH_TARGET, repo=_FOREIGN_PATH
    )
    bare = _refuse(epic_id=_BARE_EPIC, target_id=_BARE_TARGET, repo=_UNKNOWN_REPO)

    assert _OWNER_PATH in suggested.detail, suggested.detail
    assert f"{_SUGGESTION} {_PROJECT_NAME!r}" in suggested.detail, suggested.detail
    assert _SUGGESTION not in foreign.detail, foreign.detail
    assert _SUGGESTION not in bare.detail, bare.detail
