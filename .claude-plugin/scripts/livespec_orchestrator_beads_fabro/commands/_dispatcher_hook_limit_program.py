"""The in-sandbox observer that sees a repository hook outlive its limit.

WHY THE OBSERVATION HAS TO HAPPEN INSIDE THE SANDBOX, AT THE LIMIT.
`SPECIFICATION/contracts.md` section "ACP node timeouts" -> "Repository hooks
that outlive a limit" defines the event "as observed from that hook run's
processes at the moment the limit ended the operation". That moment is the only
one at which the evidence exists: a node the ENGINE ends at its timeout is
killed outright, so by the time any host-side surface reads the run record the
hook's process tree is gone and nothing can say whether it was running. The
engine also publishes no per-tool-call limit and no signal at the instant one
fires -- the finding that split the implement-node half of Scenario 177 out of
this work into `bd-ib-6p7kkd` -- but a COMMAND node's limit is its own resolved
node timeout, which the Dispatcher renders and can therefore also hand to the
node.

So `publish_draft` bounds its own push at `push_observation_budget_seconds`
below that resolved limit, and spends the reserve observing and reporting. The
push is still ended by the stage's limit; the reserve is what makes the ending
OBSERVABLE rather than a silent kill.

WHY A MATERIALIZED PROGRAM RATHER THAN SHELL IN THE NODE. The reasoning
`_dispatcher_publication_head` records applies unchanged: the observation walks
a process tree and does clock-tick arithmetic against the boot clock, and a
shell transcription of that would be a second implementation of it that no test
reads. It is STDLIB-ONLY and carries no livespec import, because the sandbox
clone is the GOVERNED repository and has no copy of this package.

IT OBSERVES AND REPORTS; IT DOES NOT REAP. The reaping obligation in the same
clause -- "every process of that hook run MUST be terminated before the agent's
next git commit or push in the same sandbox" -- is about a SECOND operation
following the first inside one agent turn, which is the implement-node half
`bd-ib-6p7kkd` owns. No second push follows `publish_draft`'s, so this program
stays an instrument and the node's own script ends the push it bounded.

THE LIMIT IS READ BACK OFF THE GRAPH THE RUN WILL USE, never re-resolved from
the repository's configuration. `publish_draft_limit_from_graph` asks the
artifact that carries the literal the node's own attribute received, so the
figure the script enforces and the figure the engine enforces cannot disagree.
A figure it cannot read is WITHHELD rather than defaulted, and the script then
pushes exactly as it did before any of this existed: an invented limit would be
enforced against a bound nobody chose and then REPORTED as the limit that ended
the push, which is worse than not observing at all.

WHICH graph is a question of its own, and `resolve_publish_draft_limit` is where
it is settled -- the overlay holds TWO candidates and only one of them can be
opened. Read its docstring before touching that choice: the written name is
relative for a package-era client, and resolving it against the Dispatcher's own
working directory finds a different repository's graph rather than failing.

THREE READINGS AN EDITOR MUST NOT INVERT.

The hook run's root is the EARLIEST-STARTED matching descendant, because the
elapsed figure the clause asks for is the HOOK RUN's, and a run that re-execs
itself (lefthook does) leaves several matching processes whose later start times
would under-report it -- the one direction that makes an over-limit hook look
like it had budget to spare.

Elapsed is measured against `/proc/uptime` and the process's own `starttime`,
never against wall-clock arithmetic over two readings: both come from the same
boot clock, so the difference is immune to the clock stepping under a long push.

And a descendant the reader could not read is SKIPPED rather than treated as
absent evidence, because a process table is a moving target -- a hook's children
exit while it is being walked, and a reader that refused on the first vanished
`stat` would report "no hook running" for the busiest possible hook run.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    node_timeout_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_over_limit import (
    HOOK_OVER_LIMIT_SENTINEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "HOOK_LIMIT_LIMITS_FILENAME",
    "HOOK_LIMIT_PROGRAM_FILENAME",
    "PUBLISH_DRAFT_NODE",
    "PUSH_OBSERVATION_RESERVE_SECONDS",
    "hook_limit_limits_path_expansion",
    "hook_limit_prepare_steps_block",
    "hook_limit_program_path_expansion",
    "hook_limit_program_source",
    "publish_draft_limit_from_graph",
    "push_observation_budget_seconds",
    "resolve_publish_draft_limit",
]

# The program and this dispatch's resolved figures, below the sandbox plugins
# root -- the same root, and for the same reason, as the publication-head reader.
HOOK_LIMIT_PROGRAM_FILENAME = "livespec-hook-limit.py"
HOOK_LIMIT_LIMITS_FILENAME = "livespec-hook-limits.env"

# The one command node this slice bounds. `pr_refresh` pushes too and takes the
# same budget, but its push republishes an already-published head, so the
# work-item scopes the observation to `publish_draft`'s first push.
PUBLISH_DRAFT_NODE = "publish_draft"

# What the node holds back from its own limit to observe and report with.
#
# It buys ONE process-tree walk plus a signal, which cost milliseconds -- so the
# figure is sized for a loaded factory host rather than for the work: hp has been
# measured at load 15-23 while at its concurrency cap, which is the condition
# this whole item exists for, and an observation that itself got starved would
# turn the one record of the ending into a second silent kill. Two minutes out of
# an hour-scale publication budget is cheap insurance; out of the 1800s default
# it is 6.7%, still smaller than the variance a loaded host contributes.
PUSH_OBSERVATION_RESERVE_SECONDS = 120


def push_observation_budget_seconds(*, limit_seconds: int) -> int:
    """The bound the node puts on its own push, given its resolved limit.

    FLOORED AT ONE SECOND rather than at zero or at the reserve. A target that
    configures a publication limit smaller than the reserve has asked for a
    budget this reserve cannot fit inside, and the two honest answers are to
    refuse the dispatch or to keep the bound meaningful; refusing would make a
    small-limit target undispatchable for a reason unrelated to its work, so the
    bound degrades to "push, then observe almost immediately". A floor of ZERO
    would instead let the wait fall through before the push could start,
    reporting every push as over-limit at zero elapsed.
    """
    return max(1, limit_seconds - PUSH_OBSERVATION_RESERVE_SECONDS)


def publish_draft_limit_from_graph(*, graph: Path) -> int | None:
    """`publish_draft`'s own rendered limit, read off the graph the run will use.

    Fail-soft to None on an unreadable graph, for the reason the module docstring
    gives: the caller withholds the figure, the node pushes unbounded, and
    nothing is reported. The alternative -- substituting the contract's default
    -- would bound the push at a number this dispatch never rendered and then
    name that number as the limit that ended it.
    """
    text = attempt(
        action=lambda: graph.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(text, AttemptFailure):
        return None
    return node_timeout_seconds(graph_text=text, node=PUBLISH_DRAFT_NODE)


def resolve_publish_draft_limit(
    *,
    graph_artifact: Path | None,
    written_graph: Path,
    warn: Callable[[str], object] | None,
) -> int | None:
    """The figure to arm this dispatch with: read off an ABSOLUTE graph, or withheld.

    WHICH PATH IS READ IS THE WHOLE POINT, and the two candidates are not
    interchangeable. `graph_artifact` is where this process can OPEN the graph;
    `written_graph` is the name the run config CARRIES, which for a package-era
    client `overlay_graph_reference` makes relative to the collected package
    because the engine refuses an absolute path in an inline file reference.

    So a RELATIVE candidate is refused as unresolvable rather than read. It is
    not an unreadable path -- it is a readable path to the WRONG file, since
    `workflow.fabro` is the conventional graph name and the Dispatcher runs from
    a repository that has one. Measured pre-fix, reading the written name armed
    the push at a decoy graph's 900s inside a 3600s stage: a bound no dispatch
    rendered, which the node would then have named as the limit that ended its
    push. Reading only an absolute path is what makes that unreachable instead
    of merely unlikely.

    `written_graph` is still the candidate for a caller that materialized no
    payload, where the written name IS the absolutized committed graph.

    And `warn` is what ends the silence. Withholding remains correct for the
    reason the module docstring gives, but every step of the degradation is
    quiet by construction -- no figure, so no figures file, so the node's own
    guard pushes unbounded -- which is exactly how a bound that never armed came
    to look like one that did.
    """
    candidate = written_graph if graph_artifact is None else graph_artifact
    limit_seconds = (
        publish_draft_limit_from_graph(graph=candidate) if candidate.is_absolute() else None
    )
    if limit_seconds is None and warn is not None:
        message = (
            f"{PUBLISH_DRAFT_NODE} hook limit withheld: no literal duration could be read"
            f" for the {PUBLISH_DRAFT_NODE} node from {candidate}, so this run's publication"
            " push is NOT bounded below its stage limit and a repository hook that outlives"
            " that limit will end the push without being named"
        )
        _ = warn(message)
    return limit_seconds


def hook_limit_program_path_expansion() -> str:
    """The shell expansion the node resolves the observer through."""
    return f"{sandbox_plugins_root_expansion()}/{HOOK_LIMIT_PROGRAM_FILENAME}"


def hook_limit_limits_path_expansion() -> str:
    """The shell expansion the node sources its two resolved figures from."""
    return f"{sandbox_plugins_root_expansion()}/{HOOK_LIMIT_LIMITS_FILENAME}"


# The materialized observer. `__SENTINEL__` is substituted from
# `HOOK_OVER_LIMIT_SENTINEL` so the line this prints and the line the host parses
# are ONE spelling -- see `_dispatcher_hook_over_limit`'s docstring on why a
# sentinel typed at both ends is the defect that makes the whole event invisible.
_PROGRAM_SOURCE = '''
import os
import sys

SENTINEL = "__SENTINEL__"
TICKS = os.sysconf("SC_CLK_TCK")


def read_text(path):
    """The file's text, or None when this reader could not read it."""
    try:
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return None


def fields_after_comm(raw):
    """A `stat` line's fields from `state` onward, so `comm` cannot shift them.

    `comm` is parenthesized and may itself contain spaces and parentheses, so the
    split is taken after the LAST close paren rather than by counting fields.
    """
    close = raw.rfind(")")
    if close < 0:
        return None
    return raw[close + 1:].split()


def process_table(proc_root):
    """{pid: (ppid, starttime_ticks)} for every process this reader can see."""
    table = {}
    try:
        names = os.listdir(proc_root)
    except OSError:
        return table
    for name in names:
        if not name.isdigit():
            continue
        raw = read_text(os.path.join(proc_root, name, "stat"))
        if raw is None:
            continue
        fields = fields_after_comm(raw)
        if fields is None or len(fields) < 20:
            continue
        try:
            table[int(name)] = (int(fields[1]), int(fields[19]))
        except ValueError:
            continue
    return table


def descendants(table, root):
    """Every transitive child of `root` in the table, root excluded."""
    children = {}
    for pid, entry in table.items():
        children.setdefault(entry[0], []).append(pid)
    found = []
    pending = list(children.get(root, ()))
    while pending:
        pid = pending.pop()
        found.append(pid)
        pending.extend(children.get(pid, ()))
    return found


def hook_run_start_ticks(proc_root, table, push_pid, hook_name):
    """The EARLIEST start among descendants whose argv names the hook, else None."""
    needle = "hooks/" + hook_name
    starts = []
    for pid in descendants(table, push_pid):
        raw = read_text(os.path.join(proc_root, str(pid), "cmdline"))
        if raw is None:
            continue
        if needle in raw.replace("\\0", " "):
            starts.append(table[pid][1])
    return min(starts) if starts else None


def uptime_seconds(proc_root):
    """Seconds since boot, on the same clock `starttime` is expressed against."""
    raw = read_text(os.path.join(proc_root, "uptime"))
    if raw is None:
        return None
    try:
        return float(raw.split()[0])
    except (IndexError, ValueError):
        return None


def option(argv, name, fallback=None):
    for index, token in enumerate(argv):
        if token == name and index + 1 < len(argv):
            return argv[index + 1]
    return fallback


def elapsed_ms(proc_root, start_ticks):
    """The hook run's elapsed milliseconds, or None when it is unmeasurable."""
    uptime = uptime_seconds(proc_root)
    if uptime is None:
        return None
    return max(0, int(round((uptime - (start_ticks / TICKS)) * 1000)))


def main(argv):
    proc_root = option(argv, "--proc-root", "/proc")
    node = option(argv, "--node")
    operation = option(argv, "--operation")
    hook_name = option(argv, "--hook-name")
    raw_pid = option(argv, "--push-pid")
    raw_limit = option(argv, "--limit-seconds")
    if not (node and operation and hook_name and raw_pid and raw_limit):
        sys.stderr.write(
            "livespec hook-limit: usage: --push-pid <pid> --node <node>"
            " --operation <commit|push> --hook-name <name> --limit-seconds <n>"
            " [--proc-root <dir>]\\n"
        )
        return 2
    try:
        push_pid = int(raw_pid)
        limit_seconds = int(raw_limit)
    except ValueError:
        sys.stderr.write("livespec hook-limit: --push-pid and --limit-seconds"
                         " must be integers\\n")
        return 2
    table = process_table(proc_root)
    start_ticks = hook_run_start_ticks(proc_root, table, push_pid, hook_name)
    if start_ticks is None:
        sys.stderr.write(
            "livespec hook-limit: no " + hook_name + " hook run was executing under"
            " pid " + str(push_pid) + " at the limit, so this is not a"
            " hook-over-limit event\\n"
        )
        return 1
    measured = elapsed_ms(proc_root, start_ticks)
    if measured is None:
        sys.stderr.write(
            "livespec hook-limit: a " + hook_name + " hook run was executing under pid "
            + str(push_pid) + " but its elapsed time could not be measured, so no"
            " hook-over-limit event is reported rather than one with an invented"
            " figure\\n"
        )
        return 1
    sys.stderr.write(
        SENTINEL + ": node=" + node + " operation=" + operation
        + " limit_seconds=" + str(limit_seconds)
        + " hook_elapsed_ms=" + str(measured) + "\\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def hook_limit_program_source() -> str:
    """The observer's exact bytes, with its one shared constant substituted.

    A function rather than a module constant for the reason
    `proof_head_program_source` gives: a reader has to be able to SEE that the
    sentinel came from `HOOK_OVER_LIMIT_SENTINEL` rather than from a literal
    typed a second time.
    """
    return _PROGRAM_SOURCE.replace("__SENTINEL__", HOOK_OVER_LIMIT_SENTINEL)


def hook_limit_prepare_steps_block(*, limit_seconds: int | None) -> str:
    """Land the observer and this dispatch's resolved figures in the sandbox.

    The two figures travel as a SOURCEABLE FILE rather than as overlay env keys
    because they have exactly one consumer -- the `publish_draft` script -- and
    the prepare step that writes the program is already the thing that has to run
    for the observation to be possible at all. One mechanism carrying both cannot
    land the program without the limit it must be invoked with.

    A WITHHELD limit renders the program and NO figures file, which is what makes
    the degradation safe rather than merely quiet: the script's own guard reads
    the absent file and pushes unbounded, exactly as it did before this existed.
    Rendering the program anyway costs nothing and keeps the two prepare steps
    from having to agree about a condition.

    Written through a heredoc with a QUOTED delimiter, so the shell expands
    nothing inside the program: the observer carries dollar-bearing,
    shell-looking text of its own.
    """
    root = sandbox_plugins_root_expansion()
    figures = (
        ""
        if limit_seconds is None
        else (
            f'cat > "{root}/{HOOK_LIMIT_LIMITS_FILENAME}" '
            f"<<'LIVESPEC_HOOK_LIMIT_FIGURES'\n"
            f"LIVESPEC_PUBLISH_DRAFT_LIMIT_SECONDS={limit_seconds}\n"
            "LIVESPEC_PUBLISH_DRAFT_PUSH_BUDGET_SECONDS="
            f"{push_observation_budget_seconds(limit_seconds=limit_seconds)}\n"
            "LIVESPEC_HOOK_LIMIT_FIGURES\n"
        )
    )
    script = (
        f'set -eu\nmkdir -p "{root}"\n'
        f'cat > "{root}/{HOOK_LIMIT_PROGRAM_FILENAME}" '
        f"<<'LIVESPEC_HOOK_LIMIT_PROGRAM'\n"
        f"{hook_limit_program_source()}"
        "LIVESPEC_HOOK_LIMIT_PROGRAM\n"
        f"{figures}"
    )
    return (
        "\n# --- Dispatcher-materialized repository-hook limit observer: the ONE\n"
        "# --- reader of a hook run's processes at the moment a command node's\n"
        "# --- resolved timeout ends its push (bd-ib-xi63mq, Scenario 177) ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )
