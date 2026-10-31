"""Drive `DetachedCommitRunner` from a run's recorded sandbox commit-runner calls.

`SPECIFICATION/contracts.md` "A commit leg completes past one tool call" and
"The recorded hook verdict outranks the agent's account of it" (work-item
`bd-ib-atyefi`). An agent that commits through the sandbox runner leaves TWO
kinds of tool call on the run's record, and neither looks like a commit to the
direct-commit reader in `_dispatcher_hook_verdict`:

- `livespec-commit-runner.py start -- git commit ...` exits 0 and prints only a
  run id, because it never waits for the commit; and
- `livespec-commit-runner.py wait <run-id> ...` exits 0 whatever the commit's
  verdict, and prints that verdict as one JSON report.

A reader keyed on the tool call's own exit status would therefore report every
runner-routed refusal as a pass. This module is where the Dispatcher reads the
REPORT instead: each `start` launches a recorded commit in an in-package
`DetachedCommitRunner`, each `wait` report is what that commit's recorded
process has observed so far, and the runner's own state machine decides what
the latest attempt's verdict is -- `running` until a terminal report arrives,
then the retained terminal state, with failed targets named by the same
normalizer a direct commit uses.

A `failed` report whose commit ran no hook -- the program says so in
`hook_ran`, judged on the whole output with the direct-commit reader's own
banner pattern, because the report's tail may have scrolled the banner off --
is not a hook refusal, exactly as a direct commit without the banner is not.

A `wait` whose `start` is not on the record (another node's, or one the stream
lost) still counts as an attempt: it is launched on first sight, because the
report alone carries the verdict.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner import (
    NO_VERDICT_STATE,
    RUNNING_STATE,
    CommitRunResult,
    DetachedCommitRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    REPORT_EXIT_CODE_KEY,
    REPORT_FAILED_TARGETS_KEY,
    REPORT_HOOK_RAN_KEY,
    REPORT_OUTPUT_TAIL_KEY,
    REPORT_RUN_ID_KEY,
    REPORT_STATE_KEY,
)

__all__: list[str] = ["CommitRunnerReplay"]

_RUNNER_CALL = re.compile(re.escape(COMMIT_RUNNER_PROGRAM_FILENAME) + r"[\"']?\s+(start|wait)\b")
_RUN_ID = re.compile(r"^commit-[0-9a-f]+$")


@dataclass
class _RecordedProcess:
    """A commit process whose observations are the run's recorded wait reports."""

    output: str = ""
    exit_code: int | None = None
    vanished: bool = False

    def poll(self, *, now: float) -> int | None:
        del now
        return self.exit_code

    def ended_without_verdict(self) -> bool:
        return self.vanished


@dataclass
class _RecordedLauncher:
    """Hands the runner a recorded process for each `start` on the run's record."""

    launched: list[_RecordedProcess] = field(default_factory=list)

    def launch(self, *, command: tuple[str, ...]) -> _RecordedProcess:
        del command
        process = _RecordedProcess()
        self.launched.append(process)
        return process


@dataclass
class _ReplayClock:
    """Replayed waits observe the record once, with a zero bound, and never sleep.

    Recorded time does not move the state machine: each `wait` report IS the
    observation, so a replay that asked to sleep would be waiting on nothing.
    """

    now: float = 0.0

    def sleep(self, *, seconds: float) -> None:
        msg = f"a replayed commit-runner wait never sleeps (asked for {seconds} s)"
        raise RuntimeError(msg)


class CommitRunnerReplay:
    """The latest runner-routed commit attempt of one stage, as its own runner sees it."""

    def __init__(self) -> None:
        self._launcher = _RecordedLauncher()
        self._runner = DetachedCommitRunner(launcher=self._launcher, clock=_ReplayClock())
        self._run_ids: dict[str, str] = {}
        self._processes: dict[str, _RecordedProcess] = {}

    def observe(self, *, command: str, output: str) -> CommitRunResult | None:
        """The attempt's current result when this completed tool call is a runner call."""
        operation = _RUNNER_CALL.search(command)
        if operation is None:
            return None
        if operation.group(1) == "start":
            return self._observe_start(command=command, output=output)
        return self._observe_wait(output=output)

    def _observe_start(self, *, command: str, output: str) -> CommitRunResult | None:
        """A new attempt, `running` until a wait report says otherwise."""
        run_id = output.strip().splitlines()[-1].strip() if output.strip() else ""
        if _RUN_ID.match(run_id) is None:
            return None
        self._launch(sandbox_run_id=run_id, command=(command,))
        return self._runner.wait(run_id=self._run_ids[run_id], timeout_seconds=0.0)

    def _observe_wait(self, *, output: str) -> CommitRunResult | None:
        """What the runner's state machine makes of one recorded wait report."""
        report = _last_report(output=output)
        if report is None:
            return None
        sandbox_run_id = report.get(REPORT_RUN_ID_KEY)
        state = report.get(REPORT_STATE_KEY)
        if not isinstance(sandbox_run_id, str) or not isinstance(state, str):
            return None
        if sandbox_run_id not in self._run_ids:
            self._launch(sandbox_run_id=sandbox_run_id, command=())
        self._record(process=self._processes[sandbox_run_id], state=state, report=report)
        result = self._runner.wait(run_id=self._run_ids[sandbox_run_id], timeout_seconds=0.0)
        if result.state == "failed" and report.get(REPORT_HOOK_RAN_KEY) is not True:
            # A commit that failed before any hook ran (nothing staged, a bad
            # message) is not a hook refusal, and the clause leaves it alone.
            return None
        return result

    def _launch(self, *, sandbox_run_id: str, command: tuple[str, ...]) -> None:
        self._run_ids[sandbox_run_id] = self._runner.start(command=command)
        self._processes[sandbox_run_id] = self._launcher.launched[-1]

    @staticmethod
    def _record(*, process: _RecordedProcess, state: str, report: dict[str, object]) -> None:
        if state == RUNNING_STATE:
            return
        exit_code = report.get(REPORT_EXIT_CODE_KEY)
        tail = report.get(REPORT_OUTPUT_TAIL_KEY)
        reported_targets = report.get(REPORT_FAILED_TARGETS_KEY)
        targets = (
            [target for target in cast("list[object]", reported_targets) if isinstance(target, str)]
            if isinstance(reported_targets, list)
            else []
        )
        target_summary = (
            "Failed targets ("
            + str(len(targets))
            + "):\n"
            + "".join("  - " + target + "\n" for target in targets)
            if targets
            else ""
        )
        process.output = target_summary + (tail if isinstance(tail, str) else "")
        if (
            state != NO_VERDICT_STATE
            and isinstance(exit_code, int)
            and not isinstance(exit_code, bool)
        ):
            process.exit_code = exit_code
        else:
            process.vanished = True


def _last_report(*, output: str) -> dict[str, object] | None:
    """The last JSON object line a `wait` printed, or None."""
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            value: object = json.loads(stripped)
        except ValueError:
            return None
        return cast("dict[str, object]", value) if isinstance(value, dict) else None
    return None
