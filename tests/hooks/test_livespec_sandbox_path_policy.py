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
) -> str | None:
    """The protected path `command` would destroy, end to end through both halves."""
    return policy.refused_path(
        targets=policy.removal_targets(command=command, working_directory=working_directory),
        resolved=resolved or {},
        protected=_protected(policy=policy),
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

    assert policy.removal_targets(command="rm -rf /tmp/one /tmp/two", working_directory=_CLONE) == (
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

    assert policy.removal_targets(
        command=f"{prefix}; rm -rf /tmp/one", working_directory=_CLONE
    ) == ("/tmp/one",)


def test_a_wrapper_still_leaves_the_removal_it_wraps_visible() -> None:
    policy = _load_policy()

    assert policy.removal_targets(command="sudo rm -rf /tmp/one", working_directory=_CLONE) == (
        "/tmp/one",
    )


@pytest.mark.parametrize("verb", ["rm", "rmdir", "unlink", "shred", "mv"])
def test_every_removing_or_moving_verb_is_read_as_destructive(verb: str) -> None:
    """`mv` is in the set because moving a protected path away removes it.

    Its DESTINATION counts too, which is why the operand list is read whole
    rather than head-first: `mv /tmp/x /workspace` replaces the root.
    """
    policy = _load_policy()

    assert policy.removal_targets(
        command=f"{verb} /tmp/one /tmp/two", working_directory=_CLONE
    ) == ("/tmp/one", "/tmp/two")


def test_a_forcing_symlink_write_is_read_as_destructive() -> None:
    """`ln -sfn` REPLACES its target, which is how a link is re-pointed."""
    policy = _load_policy()

    assert policy.removal_targets(
        command="ln -sfn /tmp/elsewhere /tmp/link", working_directory=_CLONE
    ) == ("/tmp/elsewhere", "/tmp/link")


@pytest.mark.parametrize("command", ["ln -s /tmp/a /tmp/b", "ln /tmp/a /tmp/b"])
def test_a_link_that_cannot_replace_anything_is_not_destructive(command: str) -> None:
    """Without a force flag `ln` refuses an existing target itself, so it destroys nothing."""
    policy = _load_policy()

    assert policy.removal_targets(command=command, working_directory=_CLONE) == ()


def test_the_long_force_flag_is_recognised_as_forcing() -> None:
    policy = _load_policy()

    assert policy.removal_targets(
        command="ln --force -s /tmp/a /tmp/b", working_directory=_CLONE
    ) == ("/tmp/a", "/tmp/b")


def test_an_unrelated_long_flag_is_not_mistaken_for_the_force_flag() -> None:
    policy = _load_policy()

    assert (
        policy.removal_targets(command="ln --symbolic /tmp/a /tmp/b", working_directory=_CLONE)
        == ()
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


def test_a_removal_that_names_nothing_protected_is_not_refused() -> None:
    policy = _load_policy()

    assert policy.refused_path(targets=(), resolved={}, protected=_protected(policy=policy)) is None


def test_nothing_is_refused_when_no_path_is_protected() -> None:
    """Off-sandbox the protected set is empty, so no command can be refused."""
    policy = _load_policy()

    assert (
        policy.refused_path(
            targets=(_SANDBOX_ROOT,),
            resolved={},
            protected=(),
        )
        is None
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


def test_the_destructive_verb_set_is_published() -> None:
    """The verb set is public so the guard's own documentation can name it."""
    policy = _load_policy()

    assert "rm" in policy.DESTRUCTIVE_VERBS
    assert "echo" not in policy.DESTRUCTIVE_VERBS
