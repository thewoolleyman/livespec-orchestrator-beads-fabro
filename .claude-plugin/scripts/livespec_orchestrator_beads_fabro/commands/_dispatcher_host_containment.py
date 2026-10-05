"""What the forge says about a build, and which records are host replays at all.

The IMPURE half of the host leg. `_dispatcher_host_leg` owns the evidence RULE — is
this replay evidence, and what does it decide — and this module owns everything that
rule needs GATHERED first: which of a pull request's records are replays, which
`host_recorded` record supplies the capturing identity, and whether the build each
replay names carries the merge.

WHY THE SPLIT RUNS HERE. The rule is a pure function of a record set and three
answers about it, and a rule that reached for the forge itself could not be exercised
without a double for it. The containment answer is the only thing in the host leg that
needs the network, so it is the whole of this module's reason to exist, and the join
that assembles the rule's inputs belongs beside it rather than at the call site — the
call site would otherwise decide which records count as replays, which is a decision
the rule serves.

WHY THE FORGE IS ASKED RATHER THAN THE LOCAL CLONE. A release tag is created on the
remote, and a primary checkout need never have fetched it — so a local `merge-base`
would report an unresolvable ref for a tag that plainly exists. That answer is
UNOBSERVABLE, the rule treats unobservable as a refusal, and the refusal would have
been manufactured by the instrument rather than earned by the record. Asking the forge
removes the local clone's fetch state from the question entirely.

WHY THE READER IS MEMOIZED. A capture and the replay of it are taken against ONE
installed build, so the records on a pull request routinely name the same release more
than once. An un-memoized reader spends a forge round trip per published record on
every acceptance pass, and a pass re-runs on every `reconcile-merged`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    build_identity_in,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import (
    REPLAY_VERDICTS,
    HostLeg,
    HostReplay,
    host_leg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_RECORDED,
    ProofRecord,
    latest_proof_record,
)

__all__: list[str] = [
    "ContainmentReader",
    "compare_argv",
    "containment_reader",
    "host_leg_for_records",
    "merge_contained_in",
    "unchecked_containment",
]

_COMPARE_TIMEOUT_SECONDS = 30.0
# The comparison statuses that mean `head` carries `base`: `base` is `head` itself,
# or `head` has commits beyond it. `behind` and `diverged` mean it does not. Any
# other value is a status this code does not know and is therefore unobservable
# rather than assumed either way.
_CONTAINING_STATUSES = frozenset({"ahead", "identical"})
_NOT_CONTAINING_STATUSES = frozenset({"behind", "diverged"})


class ContainmentReader(Protocol):
    """One build ref to whether it carries the merge, or `None` when unobservable.

    A Protocol rather than a `Callable[...]` alias so the parameter is KEYWORD-ONLY,
    which this tree requires of every function: a positional reader would read fine
    and then silently accept a merge sha where a ref belongs, because both are
    strings and the comparison would return a plausible answer either way.
    """

    def __call__(self, *, ref: str) -> bool | None:
        """Whether the build named `ref` carries the merge under consideration."""
        ...  # pragma: no cover - a Protocol body is never executed


def compare_argv(*, base: str, head: str) -> list[str]:
    """The forge comparison that answers whether `head` carries `base`.

    The forge is asked rather than the local clone, and that is deliberate. A release
    tag is created on the remote and a primary checkout need never have fetched it, so
    a local `merge-base` would report "unresolvable ref" for a tag that exists — an
    unobservable answer produced by the instrument rather than by the question. The
    `{owner}`/`{repo}` placeholders are `gh`'s own, resolved from the repository the
    command runs in.
    """
    return ["gh", "api", f"repos/{{owner}}/{{repo}}/compare/{base}...{head}", "--jq", ".status"]


def merge_contained_in(
    *, repo: Path, merge_sha: str, ref: str, runner: CommandRunner
) -> bool | None:
    """Whether the named build carries the merge commit, or `None` when unreadable."""
    result = runner.run(
        argv=compare_argv(base=merge_sha, head=ref),
        cwd=repo,
        timeout_seconds=_COMPARE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    status = result.stdout.strip()
    if status in _CONTAINING_STATUSES:
        return True
    if status in _NOT_CONTAINING_STATUSES:
        return False
    return None


def unchecked_containment(*, ref: str) -> bool | None:
    """The default containment answer: not checked, for every build.

    Deliberately `None` rather than `True`. A `None` answer is a REFUSAL here, so a
    caller that supplies no reader parks the item instead of closing it on a build
    nothing compared.
    """
    del ref
    return None


def containment_reader(
    *, repo: Path, merge_sha: str | None, runner: CommandRunner
) -> ContainmentReader:
    """A per-build containment answer, memoized for the life of one pass.

    MEMOIZED because two replays routinely name the same release — a capture and the
    replay of it are taken against one installed build — and an un-memoized reader
    would spend one forge round trip per published record on every pass.

    When the merge sha is unknown there is nothing to check containment OF, so every
    build answers `None` and no comparison runs. That keeps the assertion pending
    rather than passing it, reached without a comparison whose base is meaningless.
    """
    answers: dict[str, bool | None] = {}

    def contains(*, ref: str) -> bool | None:
        if merge_sha is None:
            return None
        if ref not in answers:
            answers[ref] = merge_contained_in(
                repo=repo, merge_sha=merge_sha, ref=ref, runner=runner
            )
        return answers[ref]

    return contains


def host_leg_for_records(
    *,
    assertions: Sequence[str],
    records: Sequence[ProofRecord],
    contains_merge: ContainmentReader,
) -> HostLeg:
    """The host leg of one pull request's records: select, resolve, then grade.

    The one entry point the acceptance pass uses. The three steps are kept here
    rather than at the call site so that the SELECTION — which records count as
    replays, and which `host_recorded` record supplies the capturing identity — is
    decided in the module that owns the rule those selections serve.
    """
    return host_leg(
        assertions=assertions,
        replays=_replays(records=records, contains_merge=contains_merge),
        recording_identity=_recording_identity(records=records),
    )


def _replays(
    *, records: Sequence[ProofRecord], contains_merge: ContainmentReader
) -> tuple[HostReplay, ...]:
    """Every host REPLAY record, with its parsed build and that build's containment.

    Containment is resolved only for a record that actually names a ref, so a record
    naming none costs no forge call: it is refused on the ref alone.
    """
    replays: list[HostReplay] = []
    for one in records:
        if one.verdict not in REPLAY_VERDICTS:
            continue
        build = build_identity_in(body=one.body)
        ref = None if build is None else build.containment_ref
        replays.append(
            HostReplay(
                record=one,
                build=build,
                contains_merge=None if ref is None else contains_merge(ref=ref),
            )
        )
    return tuple(replays)


def _recording_identity(*, records: Sequence[ProofRecord]) -> str | None:
    """The identity of the latest `host_recorded` record, or `None` when none exists.

    `None` means no capture was published, so no replay can be a self-replay OF one.
    That is not a licence: a replay still has to clear containment, and an assertion
    with no capture behind it is a filing problem the capture leg owns.
    """
    capture = latest_proof_record(records=records, verdict=VERDICT_HOST_RECORDED)
    return None if capture is None else capture.run_id
