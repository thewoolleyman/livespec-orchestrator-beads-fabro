"""Coverage for the sandbox path policy — what a run cannot survive losing.

Scenario 180 of `SPECIFICATION/scenarios.md` and the `contracts.md` paragraph
"The run's working tree survives the agent." put a refusal between an ACP agent
and the four paths a factory run is built out of: the sandbox root, the run's
working directory, the working-directory link the engine sets that directory
to, and the clone the link points at. These cases are the decision half of that
refusal — pure, data in and data out. The hook that supplies the data and emits
the deny payload is `livespec_sandbox_path_guard`, covered beside this file.

THE TWO HALVES ARE DELIBERATELY SEPARATE, because the policy answers two
questions that fail in opposite directions. `removal_targets` reads a command
and must be GENEROUS about what counts as destructive — a target it fails to
see is a path it cannot protect. `refused_path` compares those targets with the
protected set and must be EXACT — a protected path it reports wrongly refuses
legitimate work. Each question therefore gets its own cases rather than being
graded only through the end-to-end verdict.

THE ONE TARGET THAT CAN BE SPARED is a DESTINATION — the last operand of `mv`
or of a dereferencing `ln`, which the segment writes INTO rather than replaces
when the path is already a directory. Whether it is one is a filesystem
reading, so these cases supply it the same way they supply `resolved`: as the
`directories` argument. The default here is the EMPTY set, which is the
fail-closed reading, so every case that says nothing about directories is
grading the unspared behaviour.

The layout the cases are written against is the one the 2026-10-15 incident ran
in (run 01M4YJGC55V86C9V1X07QG3Y2H): the engine's working directory is a LINK
directly under the sandbox root, and the clone it points at lives outside that
root entirely, under `/repos`. That is why a policy keyed on "is this path
inside the sandbox root" would not protect the clone, and why the protected set
is discovered rather than assumed.

`.claude/hooks/` is not an importable package and the policy imports its
sibling shell-shape module the way a script does — off the directory it lives
in — so that directory goes on `sys.path` before the module is loaded by file
location. The load happens INSIDE each test body and the first assertion is
that the file exists, so a Red commit fails on a genuine assertion rather than
at collection time.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_POLICY_PATH = _HOOKS_DIR / "livespec_sandbox_path_policy.py"
_MODULE_NAME = "livespec_sandbox_path_policy_under_test"

_SANDBOX_ROOT = "/workspace"
_LINK = "/workspace/livespec-orchestrator-beads-fabro"
_CLONE = "/repos/thewoolleyman/livespec-orchestrator-beads-fabro"
# What the guard reads off the sandbox root: every immediate child mapped to
# what it really is. Only the one entry that resolves to the clone is the
# working-directory link; the Dispatcher-materialized siblings are not.
_SANDBOX_ENTRY_TARGETS = {
    _LINK: _CLONE,
    "/workspace/.livespec": "/workspace/.livespec",
    "/workspace/.codex": "/workspace/.codex",
}


def _load_policy() -> ModuleType:
    assert _POLICY_PATH.is_file()
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _POLICY_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _protected(*, policy: ModuleType) -> tuple[str, ...]:
    return policy.protected_paths(
        sandbox_root=_SANDBOX_ROOT,
        repository_path=_CLONE,
        repository_clone=_CLONE,
        sandbox_entry_targets=_SANDBOX_ENTRY_TARGETS,
    )


def _refused(
    *,
    policy: ModuleType,
    command: str,
    working_directory: str = _CLONE,
    resolved: dict[str, str] | None = None,
    directories: set[str] | None = None,
) -> str | None:
    """The protected path `command` would destroy, end to end through both halves."""
    return policy.refused_path(
        targets=policy.removal_targets(command=command, working_directory=working_directory),
        resolved=resolved or {},
        directories=directories or set(),
        protected=_protected(policy=policy),
    )


def _target_paths(
    *, policy: ModuleType, command: str, working_directory: str = _CLONE
) -> tuple[str, ...]:
    """Just the paths a command acts on, for cases whose subject is not the mark."""
    return tuple(
        target.path
        for target in policy.removal_targets(command=command, working_directory=working_directory)
    )


# ---------------------------------------------------------------------------
# protected_paths — which paths the run cannot survive losing
# ---------------------------------------------------------------------------


def test_the_sandbox_root_its_working_directory_link_and_the_clone_are_protected() -> None:
    policy = _load_policy()

    assert _protected(policy=policy) == (_SANDBOX_ROOT, _LINK, _CLONE)


def test_a_sibling_under_the_sandbox_root_that_is_not_the_clone_is_not_a_link() -> None:
    """Only the entry resolving to the clone is the working-directory link.

    Without this the Dispatcher's own materialized paths — the credential-use
    guard, the projected Codex home, the tmux socket root — would each be
    protected, and `rm -rf /workspace/.tmux` would be refused.
    """
    policy = _load_policy()

    assert "/workspace/.livespec" not in _protected(policy=policy)
    assert "/workspace/.codex" not in _protected(policy=policy)


def test_a_clone_that_is_the_sandbox_root_itself_collapses_to_one_protected_path() -> None:
    """The Petri-era layout, where the repository clone IS `/workspace`."""
    policy = _load_policy()

    assert policy.protected_paths(
        sandbox_root=_SANDBOX_ROOT,
        repository_path=_SANDBOX_ROOT,
        repository_clone=_SANDBOX_ROOT,
        sandbox_entry_targets={},
    ) == (_SANDBOX_ROOT,)


def test_a_clone_directly_under_the_sandbox_root_is_protected_without_a_link() -> None:
    """The pinned-engine layout, where the clone is a real `/workspace/<repo>`."""
    policy = _load_policy()
    pinned = "/workspace/livespec-orchestrator-beads-fabro"

    assert policy.protected_paths(
        sandbox_root=_SANDBOX_ROOT,
        repository_path=pinned,
        repository_clone=pinned,
        sandbox_entry_targets={pinned: pinned},
    ) == (_SANDBOX_ROOT, pinned)


def test_a_repository_the_sandbox_root_does_not_hold_protects_nothing() -> None:
    """OUTSIDE a factory sandbox the policy is inert, which is the clause's scope.

    The governing paragraph protects the run's layout inside the sandbox. A
    guard that also refused a removal in a developer's own checkout would be
    enforcing a rule nobody ratified, so the discriminator is the LAYOUT: the
    sandbox root holds the repository, directly or through a link to it.
    """
    policy = _load_policy()

    assert (
        policy.protected_paths(
            sandbox_root=_SANDBOX_ROOT,
            repository_path="/data/projects/livespec-orchestrator-beads-fabro",
            repository_clone="/data/projects/livespec-orchestrator-beads-fabro",
            sandbox_entry_targets={_LINK: _CLONE},
        )
        == ()
    )


@pytest.mark.parametrize(("sandbox_root", "repository_path"), [("", _CLONE), (_SANDBOX_ROOT, "")])
def test_an_unresolvable_sandbox_root_or_repository_protects_nothing(
    sandbox_root: str, repository_path: str
) -> None:
    """A path the guard could not read is not a path it can defend.

    This arm is not caution: the entry point derives the repository from the
    hook payload, so an unmodelled payload shape yields an empty string, and a
    policy that treated that as the filesystem root would refuse every removal
    in the session.
    """
    policy = _load_policy()

    assert (
        policy.protected_paths(
            sandbox_root=sandbox_root,
            repository_path=repository_path,
            repository_clone=repository_path,
            sandbox_entry_targets=_SANDBOX_ENTRY_TARGETS,
        )
        == ()
    )


# ---------------------------------------------------------------------------
# removal_targets — what an executed destructive segment would act on
# ---------------------------------------------------------------------------


def test_a_removal_names_its_operands_and_not_its_flags() -> None:
    policy = _load_policy()

    assert _target_paths(policy=policy, command="rm -rf /tmp/one /tmp/two") == (
        "/tmp/one",
        "/tmp/two",
    )


def test_a_command_whose_leading_word_is_not_destructive_acts_on_nothing() -> None:
    policy = _load_policy()

    assert policy.removal_targets(command="git status --short", working_directory=_CLONE) == ()


def test_a_command_the_shell_lexer_cannot_split_acts_on_nothing() -> None:
    """The ONE sanctioned fail-open: a lexer error must not refuse real work."""
    policy = _load_policy()

    assert policy.removal_targets(command='echo "unbalanced', working_directory=_CLONE) == ()


def test_an_empty_command_acts_on_nothing() -> None:
    policy = _load_policy()

    assert policy.removal_targets(command="", working_directory=_CLONE) == ()


@pytest.mark.parametrize("prefix", ["sudo", "env FOO=1", "mise exec --"])
def test_a_segment_that_executes_nothing_acts_on_nothing(prefix: str) -> None:
    """A segment of pure wrappers, assignments and flags runs no command.

    It still has to be WALKED rather than skipped, because the segment after it
    is where the removal lives.
    """
    policy = _load_policy()

    assert _target_paths(policy=policy, command=f"{prefix}; rm -rf /tmp/one") == ("/tmp/one",)


def test_a_wrapper_still_leaves_the_removal_it_wraps_visible() -> None:
    policy = _load_policy()

    assert _target_paths(policy=policy, command="sudo rm -rf /tmp/one") == ("/tmp/one",)


@pytest.mark.parametrize("verb", ["rm", "rmdir", "unlink", "shred", "mv"])
def test_every_removing_or_moving_verb_is_read_as_destructive(verb: str) -> None:
    """`mv` is in the set because moving a protected path away removes it.

    Its DESTINATION is read too, which is why the operand list is read whole
    rather than head-first — `mv /tmp/x /workspace` names the root in its
    SECOND word. Whether that word is a path the command destroys is the
    separate question the destination mark below carries.
    """
    policy = _load_policy()

    assert _target_paths(policy=policy, command=f"{verb} /tmp/one /tmp/two") == (
        "/tmp/one",
        "/tmp/two",
    )


def test_a_forcing_symlink_write_is_read_as_destructive() -> None:
    """`ln -sfn` REPLACES its target, which is how a link is re-pointed."""
    policy = _load_policy()

    assert _target_paths(policy=policy, command="ln -sfn /tmp/elsewhere /tmp/link") == (
        "/tmp/elsewhere",
        "/tmp/link",
    )


@pytest.mark.parametrize("command", ["ln -s /tmp/a /tmp/b", "ln /tmp/a /tmp/b"])
def test_a_link_that_cannot_replace_anything_is_not_destructive(command: str) -> None:
    """Without a force flag `ln` refuses an existing target itself, so it destroys nothing."""
    policy = _load_policy()

    assert policy.removal_targets(command=command, working_directory=_CLONE) == ()


def test_the_long_force_flag_is_recognised_as_forcing() -> None:
    policy = _load_policy()

    assert _target_paths(policy=policy, command="ln --force -s /tmp/a /tmp/b") == (
        "/tmp/a",
        "/tmp/b",
    )


def test_an_unrelated_long_flag_is_not_mistaken_for_the_force_flag() -> None:
    policy = _load_policy()

    assert (
        policy.removal_targets(command="ln --symbolic /tmp/a /tmp/b", working_directory=_CLONE)
        == ()
    )


# ---------------------------------------------------------------------------
# removal_targets — which operand is a DESTINATION rather than a casualty
# ---------------------------------------------------------------------------


def test_the_last_operand_of_a_move_is_marked_as_the_destination_it_writes_into() -> None:
    """`mv` and `ln` write their last operand; every other operand is consumed.

    The mark travels WITH the path rather than as a set of paths, because one
    command can carry the same path in both roles — which is what the
    later-segment case below grades.
    """
    policy = _load_policy()

    assert policy.removal_targets(command="mv /tmp/one /tmp/two", working_directory=_CLONE) == (
        policy.Target(path="/tmp/one", into_directory=False),
        policy.Target(path="/tmp/two", into_directory=True),
    )


def test_a_removal_marks_no_operand_as_a_destination() -> None:
    """`rm` writes nothing, so each of its operands is destroyed outright."""
    policy = _load_policy()

    assert policy.removal_targets(command="rm -rf /tmp/one /tmp/two", working_directory=_CLONE) == (
        policy.Target(path="/tmp/one", into_directory=False),
        policy.Target(path="/tmp/two", into_directory=False),
    )


def test_a_lone_operand_is_never_a_destination() -> None:
    """A destination means nothing without a source beside it.

    `mv /workspace` is an error the shell reports without touching anything,
    and `ln -s /workspace` links INTO the working directory rather than
    writing the word it names — so neither writes that operand, and sparing it
    would spare a word this module has not modelled a destination for.
    """
    policy = _load_policy()

    assert policy.removal_targets(command=f"mv {_SANDBOX_ROOT}", working_directory=_CLONE) == (
        policy.Target(path=_SANDBOX_ROOT, into_directory=False),
    )


def test_a_link_asked_not_to_dereference_replaces_its_destination() -> None:
    """`ln -sfn` RE-POINTS a link to a directory instead of writing inside it.

    This is the exception inside the exception, and the one that matters most
    here: the engine's own working-directory link IS such a link, and the
    filesystem reports it as a directory whichever way the command means it.
    Only the command's own flags separate the two readings.
    """
    policy = _load_policy()

    assert policy.removal_targets(
        command=f"ln -sfn /tmp/elsewhere {_LINK}", working_directory=_CLONE
    ) == (
        policy.Target(path="/tmp/elsewhere", into_directory=False),
        policy.Target(path=_LINK, into_directory=False),
    )


def test_the_long_no_dereference_flag_is_recognised_too() -> None:
    policy = _load_policy()

    assert policy.removal_targets(
        command=f"ln --force --no-dereference -s /tmp/elsewhere {_LINK}", working_directory=_CLONE
    ) == (
        policy.Target(path="/tmp/elsewhere", into_directory=False),
        policy.Target(path=_LINK, into_directory=False),
    )


# The four spellings of "treat the last operand as a plain name" that the
# `-n` reading alone cannot see. They are listed once and graded twice, because
# the mark and the refusal are separate questions: the mark is what
# `removal_targets` decides from the command, and the refusal is what
# `refused_path` decides once the filesystem has reported that operand a
# directory — which it does for every one of these, exactly as it does for an
# ordinary destination.
_PLAIN_DESTINATION_COMMANDS = [
    f"mv -T /tmp/x {_LINK}",
    f"mv --no-target-directory /tmp/x {_LINK}",
    f"ln -sfT /tmp/elsewhere {_LINK}",
    f"ln -sf --no-target-directory /tmp/elsewhere {_LINK}",
]


@pytest.mark.parametrize("command", _PLAIN_DESTINATION_COMMANDS)
def test_no_target_directory_makes_the_last_operand_a_replacement(command: str) -> None:
    """`-T` is the same semantic as `ln -n`, and it is `mv`'s ONLY spelling of it.

    coreutils gives both verbs `-T` / `--no-target-directory`, "treat DEST as a
    normal file", so under it `ln` RE-POINTS a link instead of writing through
    it and `mv` overwrites the name instead of moving inside it. Measured
    against real coreutils on an isolated layout mirroring this one: `mv -T
    <file> <link-to-directory>` exits 0, leaves a regular file where the link
    was, and a later `cd` into it fails `Not a directory` — which is the
    engine's own run-ending condition from the 2026-10-15 incident.
    """
    policy = _load_policy()

    assert policy.removal_targets(command=command, working_directory=_CLONE)[-1] == policy.Target(
        path=_LINK, into_directory=False
    )


def test_a_no_clobber_move_still_has_a_destination() -> None:
    """`-n` is read only for `ln`: on GNU `mv` it is `--no-clobber` and means another thing.

    Reading it for `mv` as well would turn the commonest safe move an agent
    types into a refusal, on a flag whose whole purpose is to destroy less.
    """
    policy = _load_policy()

    assert policy.removal_targets(
        command=f"mv -n /tmp/patch.diff {_CLONE}", working_directory=_CLONE
    ) == (
        policy.Target(path="/tmp/patch.diff", into_directory=False),
        policy.Target(path=_CLONE, into_directory=True),
    )


# ---------------------------------------------------------------------------
# refused_path — the refusal, and what it names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("protected_path", [_SANDBOX_ROOT, _LINK, _CLONE])
def test_removing_any_protected_path_is_refused_and_names_that_path(protected_path: str) -> None:
    """Assertion 1 of the Definition of Done, one protected path at a time."""
    policy = _load_policy()

    assert _refused(policy=policy, command=f"rm -rf {protected_path}") == protected_path


def test_moving_a_protected_path_away_is_refused() -> None:
    policy = _load_policy()

    assert _refused(policy=policy, command=f"mv {_SANDBOX_ROOT} /tmp/elsewhere") == _SANDBOX_ROOT


def test_replacing_a_protected_path_through_a_forced_link_is_refused() -> None:
    policy = _load_policy()

    assert _refused(policy=policy, command=f"ln -sfn /tmp/elsewhere {_LINK}") == _LINK


# ---------------------------------------------------------------------------
# refused_path — a destination that is already a directory destroys nothing
# ---------------------------------------------------------------------------


def test_a_move_into_a_destination_that_is_already_a_directory_is_not_refused() -> None:
    """The governing clause's own allowance, in the shape an agent reaches for.

    `mv /tmp/patch.diff <clone>` moves a scratch file INTO the tree and
    replaces nothing, so its executed segment moves only paths that are not
    protected paths. Refusing it stops an implement agent restoring a scratch
    file, which this repository's own Red-Green protocol prescribes.
    """
    policy = _load_policy()

    assert (
        _refused(policy=policy, command=f"mv /tmp/patch.diff {_CLONE}", directories={_CLONE})
        is None
    )


@pytest.mark.parametrize(("written", "directory"), [(".", _CLONE), ("..", "/repos/thewoolleyman")])
def test_a_move_into_the_working_directory_or_its_parent_is_not_refused(
    written: str, directory: str
) -> None:
    """The same allowance in the relative forms an agent actually types.

    Both resolve onto the protected set — `.` IS the clone and `..` is an
    ancestor of it — so neither is spared by the path comparison. Only the
    destination reading separates them from a removal.
    """
    policy = _load_policy()

    assert (
        _refused(policy=policy, command=f"mv /tmp/patch.diff {written}", directories={directory})
        is None
    )


def test_a_link_written_inside_a_protected_directory_is_not_refused() -> None:
    """`ln -sf` without no-dereference creates INSIDE the directory it names."""
    policy = _load_policy()

    assert (
        _refused(policy=policy, command=f"ln -sf /tmp/elsewhere {_LINK}", directories={_LINK})
        is None
    )


def test_repointing_the_working_directory_link_is_refused_even_as_a_directory() -> None:
    """The filesystem cannot settle this one, and the flags can.

    `ln -sfn /tmp/elsewhere <link>` destroys the link the engine sets its
    working directory to, while the reading that spares an ordinary
    destination reports that same link as a directory. A build that applied
    the reading unconditionally would allow the incident's nearest neighbour.
    """
    policy = _load_policy()

    assert (
        _refused(policy=policy, command=f"ln -sfn /tmp/elsewhere {_LINK}", directories={_LINK})
        == _LINK
    )


@pytest.mark.parametrize("command", _PLAIN_DESTINATION_COMMANDS)
def test_a_plain_destination_spelling_is_refused_even_as_a_directory(command: str) -> None:
    """The `-T` half of the trap the `ln -sfn` case above describes.

    `_is_directory` follows the link, so the filesystem reports it as a
    directory under every one of these spellings just as it does under an
    ordinary destination — and every one of them destroys it. A build reading
    only `-n` allowed all four, which is the unsafe direction: an allowance of
    a run-ending command rather than an over-refusal.
    """
    policy = _load_policy()

    assert _refused(policy=policy, command=command, directories={_LINK}) == _LINK


def test_moving_a_protected_path_away_is_still_refused_when_its_destination_exists() -> None:
    """The SOURCE side is untouched by the destination reading.

    `mv /workspace /tmp/moved-root` really does move the root away, and
    assertion 1 depends on refusing it — so sparing ONE operand must never
    read as sparing the operand list.
    """
    policy = _load_policy()

    assert (
        _refused(
            policy=policy,
            command=f"mv {_SANDBOX_ROOT} /tmp/moved-root",
            directories={_SANDBOX_ROOT, "/tmp/moved-root"},
        )
        == _SANDBOX_ROOT
    )


def test_a_destination_a_later_segment_then_removes_is_still_refused() -> None:
    """The reading is applied per TARGET, never per path.

    `mv /tmp/x /workspace && rm -rf /workspace` writes into the root and then
    removes it. Sparing by VALUE would spare the removal too, and the whole
    command would read as an ordinary move.
    """
    policy = _load_policy()

    assert (
        _refused(
            policy=policy,
            command=f"mv /tmp/x {_SANDBOX_ROOT} && rm -rf {_SANDBOX_ROOT}",
            directories={_SANDBOX_ROOT},
        )
        == _SANDBOX_ROOT
    )


def test_a_destination_the_reading_did_not_find_is_still_a_replacement() -> None:
    """Nothing is spared on a reading that found no directory — the fail-closed arm."""
    policy = _load_policy()

    assert _refused(policy=policy, command=f"mv /tmp/x {_SANDBOX_ROOT}") == _SANDBOX_ROOT


def test_a_mixed_removal_that_also_names_a_protected_path_is_refused_and_names_it() -> None:
    """Assertion 7: the scratch operand does not license the protected one.

    This is the case the ratification review caught in the proposal's first
    draft, where the scratch-directory allowance read as an exemption for the
    whole command rather than for that one operand.
    """
    policy = _load_policy()

    assert _refused(policy=policy, command=f"rm -rf /tmp/layout-sim {_SANDBOX_ROOT}") == (
        _SANDBOX_ROOT
    )


@pytest.mark.parametrize("reference", ['"$d"', '"${d}"', "$d"])
def test_a_removal_through_a_variable_this_command_assigned_is_refused(reference: str) -> None:
    """Assertion 5: the protected path is named once, in a word that is not an operand.

    The assignment and the removal are different segments, so the value a name
    carries is the second piece of state the walk has to hold — alongside the
    working directory — before a later word can be read at all.
    """
    policy = _load_policy()

    assert _refused(policy=policy, command=f"d={_SANDBOX_ROOT}; rm -rf {reference}") == (
        _SANDBOX_ROOT
    )


def test_a_variable_holding_a_scratch_path_is_not_refused() -> None:
    policy = _load_policy()

    assert _refused(policy=policy, command='d=/tmp/layout-sim; rm -rf "$d"') is None


def test_a_longer_variable_name_is_substituted_before_its_own_prefix() -> None:
    """Substituting `d` before `dd` would rewrite the `$d` inside `$dd`.

    This is the one ordering in the substitution that is not interchangeable,
    and getting it backwards produces a word that matches nothing while
    reporting a clean allow.
    """
    policy = _load_policy()

    assert (
        _refused(policy=policy, command=f'd=/tmp/one; dd={_SANDBOX_ROOT}; rm -rf "$dd"')
        == _SANDBOX_ROOT
    )


def test_a_variable_this_command_never_assigned_is_left_unexpanded() -> None:
    """A value the environment carries is not in the command, so it is not guessed.

    Leaving the reference unexpanded is what keeps the word from matching
    anything: a guard that substituted its own environment would be deciding
    against a value the agent's shell may never see.
    """
    policy = _load_policy()

    assert _refused(policy=policy, command='rm -rf "$LIVESPEC_NOT_ASSIGNED_HERE"') is None


def test_a_cd_through_a_variable_moves_the_directory_a_later_word_is_read_from() -> None:
    """The directory and the variable interact, so both pieces of state are expanded."""
    policy = _load_policy()

    assert _refused(policy=policy, command='d=/; cd "$d" && rm -rf workspace') == _SANDBOX_ROOT


def test_a_relative_removal_after_changing_into_a_parent_is_refused() -> None:
    """Assertion 3, and Scenario 180's second scenario verbatim.

    The `cd` and the removal are different segments, so the directory a later
    word is read from is state the walk has to carry. Without it `workspace/`
    resolves against the ORIGINAL working directory, lands inside the
    repository tree, and reports a clean allow.
    """
    policy = _load_policy()

    assert _refused(policy=policy, command="cd / && rm -rf workspace/") == _SANDBOX_ROOT


def test_a_bare_cd_leaves_the_last_known_directory_in_place() -> None:
    """A `cd` with no operand goes somewhere this module cannot know.

    Keeping the last KNOWN directory is the deliberate direction: resolving
    later relative words against a home directory the guard invented would
    make every one of those readings fiction. The cost is a possible refusal
    of a removal that would have happened elsewhere, which an absolute path
    avoids; the alternative cost is losing the run.
    """
    policy = _load_policy()

    assert _refused(policy=policy, command="cd && rm -rf .") == _CLONE


def test_a_trailing_slash_does_not_hide_a_protected_path() -> None:
    """Assertion 3: `/workspace/` and `/workspace` are the same directory."""
    policy = _load_policy()

    assert _refused(policy=policy, command=f"rm -rf {_SANDBOX_ROOT}/") == _SANDBOX_ROOT


def test_a_glob_that_expands_to_a_protected_path_is_refused() -> None:
    """Assertion 3: the shell would hand `rm` the protected path itself.

    Matched as a PATTERN against the protected set rather than expanded,
    because expansion needs the filesystem and this module has none — and
    because the question is only ever whether a protected path is among what
    the shell would produce.
    """
    policy = _load_policy()

    assert _refused(policy=policy, command="rm -rf /works*") == _SANDBOX_ROOT


def test_a_glob_under_the_sandbox_root_reaches_the_working_directory_link() -> None:
    """`rm -rf /workspace/*` removes the link, which ends the run as surely."""
    policy = _load_policy()

    assert _refused(policy=policy, command=f"rm -rf {_SANDBOX_ROOT}/*") == _LINK


def test_a_glob_under_a_scratch_directory_is_not_refused() -> None:
    policy = _load_policy()

    assert _refused(policy=policy, command="rm -rf /tmp/*") is None


def test_a_glob_that_empties_the_repository_tree_is_not_refused() -> None:
    """`rm -rf *` from the repository root is in-tree, and v142 allows it.

    Recorded as a case rather than left implicit because it is the boundary of
    this guard: emptying the tree, or removing the clone's `.git`, is tracked
    separately as bd-ib-quzpge and is deliberately NOT refused here.
    """
    policy = _load_policy()

    assert _refused(policy=policy, command="rm -rf *") is None


def test_removing_the_working_directory_itself_as_a_dot_is_refused() -> None:
    """Assertion 4: `rm -rf .` from the unchanged working directory IS the clone."""
    policy = _load_policy()

    assert _refused(policy=policy, command="rm -rf .") == _CLONE


def test_removing_the_parent_of_the_working_directory_is_refused() -> None:
    """Assertion 4: a directory ABOVE a protected path destroys it just as surely.

    `rm -rf ..` from the clone removes the directory the clone sits in, so
    nothing it contains survives — which is why the comparison includes every
    ancestor, and why this refusal names the CLONE rather than the ancestor the
    command wrote.
    """
    policy = _load_policy()

    assert _refused(policy=policy, command="rm -rf ..") == _CLONE


def test_a_non_canonical_spelling_of_a_protected_path_is_refused() -> None:
    """Assertion 4: `/tmp/../workspace` is `/workspace` spelled the long way."""
    policy = _load_policy()

    assert _refused(policy=policy, command="rm -rf /tmp/../workspace") == _SANDBOX_ROOT


def test_removing_the_directory_that_holds_the_clone_tree_is_refused() -> None:
    """The ancestry rule reaches the whole chain, not only the immediate parent."""
    policy = _load_policy()

    assert _refused(policy=policy, command="rm -rf /repos") == _CLONE


def test_a_relative_path_inside_the_repository_tree_is_not_refused() -> None:
    """Resolution against the working directory must not over-reach downward.

    A path BELOW a protected path is in-tree, so it resolves to something the
    protected set does not hold — the allowance half of assertion 8, written in
    the relative form an agent actually types.
    """
    policy = _load_policy()

    assert _refused(policy=policy, command="rm -f tests/conftest.py") is None


def test_a_removal_under_a_scratch_directory_is_not_refused() -> None:
    """Assertion 8, first half."""
    policy = _load_policy()

    assert _refused(policy=policy, command="rm -rf /tmp/layout-sim") is None


def test_removing_a_file_inside_the_repository_tree_is_not_refused() -> None:
    """Assertion 8, second half. Emptying the tree is in-tree and v142 allows it."""
    policy = _load_policy()

    assert _refused(policy=policy, command=f"rm -f {_CLONE}/tests/conftest.py") is None


def test_a_protected_path_passed_to_echo_is_not_refused() -> None:
    """Assertion 9, first half: a word a shell would print is not a word it would run."""
    policy = _load_policy()

    assert _refused(policy=policy, command=f'echo "rm -rf {_SANDBOX_ROOT}"') is None


def test_a_target_whose_resolution_is_a_protected_path_is_refused() -> None:
    """What the caller resolved a target to counts as much as what was written.

    The pairing is supplied rather than computed because this module has no
    filesystem; the hook beside it reads the real links.
    """
    policy = _load_policy()

    assert (
        _refused(
            policy=policy,
            command="rm -rf /tmp/agent-made-link",
            resolved={"/tmp/agent-made-link": _SANDBOX_ROOT},
        )
        == _SANDBOX_ROOT
    )


def test_a_target_whose_resolution_is_unprotected_is_not_refused() -> None:
    policy = _load_policy()

    assert (
        _refused(
            policy=policy,
            command="rm -rf /tmp/agent-made-link",
            resolved={"/tmp/agent-made-link": "/tmp/layout-sim"},
        )
        is None
    )


def test_a_protected_path_inside_a_here_document_body_is_not_refused() -> None:
    """Assertion 9, second half: a body is file data, so its words are not commands.

    The body carries a `&&`, and that is what makes the case bite rather than
    being a formality. Without dropping bodies BEFORE the command is read, the
    segment walk splits on that operator and takes the body's second half for a
    command the shell would run — so writing a test fixture about the incident
    would be refused as if it were the incident.
    """
    policy = _load_policy()
    command = (
        "cat > layout-sim.sh <<'EOF'\n"
        f"cd /tmp && rm -rf {_SANDBOX_ROOT} && mkdir -p {_SANDBOX_ROOT}\n"
        "EOF"
    )

    assert _refused(policy=policy, command=command) is None


def test_a_removal_on_the_line_after_a_closed_here_document_is_still_refused() -> None:
    """Dropping bodies must not swallow the commands that follow one."""
    policy = _load_policy()
    command = f"cat > note.txt <<'EOF'\njust prose\nEOF\nrm -rf {_SANDBOX_ROOT}"

    assert _refused(policy=policy, command=command) == _SANDBOX_ROOT


def test_a_removal_that_names_nothing_protected_is_not_refused() -> None:
    policy = _load_policy()

    assert (
        policy.refused_path(
            targets=(), resolved={}, directories=set(), protected=_protected(policy=policy)
        )
        is None
    )


def test_nothing_is_refused_when_no_path_is_protected() -> None:
    """Off-sandbox the protected set is empty, so no command can be refused."""
    policy = _load_policy()

    assert (
        policy.refused_path(
            targets=(policy.Target(path=_SANDBOX_ROOT, into_directory=False),),
            resolved={},
            directories=set(),
            protected=(),
        )
        is None
    )


# ---------------------------------------------------------------------------
# stand_in_targets — the word a refusal has to quote to be actionable
# ---------------------------------------------------------------------------


def test_a_link_the_command_wrote_is_a_stand_in_for_the_path_it_resolves_to() -> None:
    """The refusal names a path this command never wrote; this is why.

    Measured 2026-10-18 on run 01M577JN5RK7220F6B50PN1227: `rm -f
    /tmp/proof-capture/agent-made-link` was refused naming `/workspace`, which
    appears nowhere in it, and the remedy the message gave — build the
    simulation under /tmp — was the one the agent had already followed.
    """
    policy = _load_policy()
    link = "/tmp/layout-sim/agent-made-link"

    assert policy.stand_in_targets(
        targets=(policy.Target(path=link, into_directory=False),),
        resolved={link: _SANDBOX_ROOT},
        directories=set(),
        protected=_protected(policy=policy),
    ) == (link,)


def test_a_target_naming_a_protected_path_outright_is_not_a_stand_in() -> None:
    """The message already names it, so quoting it again explains nothing."""
    policy = _load_policy()

    assert (
        policy.stand_in_targets(
            targets=(policy.Target(path=_SANDBOX_ROOT, into_directory=False),),
            resolved={},
            directories=set(),
            protected=_protected(policy=policy),
        )
        == ()
    )


def test_a_glob_is_never_a_stand_in() -> None:
    """A pattern is matched rather than resolved, so it stands in for nothing."""
    policy = _load_policy()
    pattern = f"{_SANDBOX_ROOT}/*"

    assert (
        policy.stand_in_targets(
            targets=(policy.Target(path=pattern, into_directory=False),),
            resolved={pattern: _SANDBOX_ROOT},
            directories=set(),
            protected=_protected(policy=policy),
        )
        == ()
    )


def test_a_spared_destination_is_not_a_stand_in_for_another_targets_refusal() -> None:
    """A destination written INTO is not refused, so it explains no refusal.

    `mv /tmp/x <link-to-clone> && rm -rf /workspace` is refused for the root.
    Naming the destination would blame the one operand that destroyed nothing.
    """
    policy = _load_policy()
    destination = "/tmp/layout-sim/link-to-clone"

    assert (
        policy.stand_in_targets(
            targets=(
                policy.Target(path=destination, into_directory=True),
                policy.Target(path=_SANDBOX_ROOT, into_directory=False),
            ),
            resolved={destination: _CLONE},
            directories={destination},
            protected=_protected(policy=policy),
        )
        == ()
    )


# ---------------------------------------------------------------------------
# refusal_message — the operator-facing refusal
# ---------------------------------------------------------------------------


def test_the_refusal_message_names_the_protected_path_and_the_command() -> None:
    policy = _load_policy()
    command = f"cd /tmp && rm -rf {_SANDBOX_ROOT}"

    message = policy.refusal_message(protected_path=_SANDBOX_ROOT, command=command)

    assert _SANDBOX_ROOT in message
    assert f"Command: {command}" in message
    assert "Do NOT retry" in message


def test_the_refusal_message_quotes_a_stand_in_and_says_the_link_is_permanent() -> None:
    """Without this the agent cannot tell why a /tmp-only command was refused."""
    policy = _load_policy()
    link = "/tmp/layout-sim/agent-made-link"

    message = policy.refusal_message(
        protected_path=_SANDBOX_ROOT, command=f"rm -f {link}", stand_ins=(link,)
    )

    assert link in message
    assert f"does not name {_SANDBOX_ROOT}" in message
    assert "cannot be cleaned up" in message
    assert "no earlier run has used" in message


def test_the_refusal_message_omits_the_disclosure_when_the_command_named_the_path() -> None:
    """A command that wrote the path down needs no explanation of how it matched."""
    policy = _load_policy()

    message = policy.refusal_message(
        protected_path=_SANDBOX_ROOT, command=f"rm -rf {_SANDBOX_ROOT}", stand_ins=()
    )

    assert "does not name" not in message


def test_the_destructive_verb_set_is_published() -> None:
    """The verb set is public so the guard's own documentation can name it."""
    policy = _load_policy()

    assert "rm" in policy.DESTRUCTIVE_VERBS
    assert "echo" not in policy.DESTRUCTIVE_VERBS
