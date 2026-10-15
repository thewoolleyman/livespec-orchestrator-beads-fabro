"""The ONE place this package knows a sandbox container is a Docker container.

The sandbox containers run where the Fabro server runs, so every port is
opened onto ONE NAMED DAEMON — the factory's, carried as `docker_host` and
rendered as the Docker CLI's own `--host` option. It is required rather than
optional because a port that could be built without one is a port that
reaches whichever daemon the Dispatcher happens to be running beside, which
on this fleet is a host that has never started a sandbox container: the
sweep then journals `containers_observed: 0` for a factory leaking twelve of
them, and that record is indistinguishable at every field from a clean
factory. `_dispatcher_reconcile_runs_containers.py` owns which daemons a
pass addresses and why an undeclared one is reported rather than guessed.

TWO READS RATHER THAN ONE, because `docker ps --format` exposes no memory
limit at all. The listing answers which containers exist and the inspect
answers what each one was limited to, and the second is skipped entirely when
the first found nothing — a healthy host is the common case and must not pay
a round trip to confirm it.

AN UNREADABLE INVENTORY IS REPORTED, NEVER READ AS AN EMPTY HOST. A daemon
that is down, a `docker` that is absent from the Dispatcher's PATH, and a
host with no leaked container all produce zero container names; only
`observed` separates the first two from the third. Without it a sweep that
had gone blind would journal exactly what a sweep over a clean host journals,
which is the one absence this whole lane exists to rule out.

THE MEMORY LIMIT IS A RECORD FIELD AND NEVER A SAFETY INPUT, so an inspect
that fails leaves every limit `None` and the removal proceeds. Treating an
unreadable limit as a reason to hold would let one broken field keep a dead
run's container alive; reporting a zero instead would assert a measurement
that was never taken.

The listing is deliberately scoped to the RUNNING population — `docker ps`
without `-a` — because that is the population that spends the slice's
envelope. An exited container holds no memory and its removal would discard
a terminal run's logs for no reclaim at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_sweep import (
    SANDBOX_CONTAINER_NAME_PREFIX,
    SandboxContainer,
    container_run_id,
)

__all__: list[str] = [
    "DOCKER_BIN",
    "SandboxContainerInventory",
    "SandboxContainerPort",
]

DOCKER_BIN = "docker"

# The CLI's global daemon-address option. It precedes the verb; passed after
# one, the CLI reads it as that verb's own flag and refuses.
_HOST_OPTION = "--host"

_PS_TIMEOUT_SECONDS = 60.0
_INSPECT_TIMEOUT_SECONDS = 60.0
_REMOVE_TIMEOUT_SECONDS = 120.0

# `.Name` renders with a leading slash; the limit is `HostConfig.Memory`, in
# bytes, and `0` is how the daemon spells "no limit of its own".
_INSPECT_FORMAT = "{{.Name}}\t{{.HostConfig.Memory}}"
_INSPECT_FIELD_SEPARATOR = "\t"
_DOCKER_NAME_PREFIX = "/"


@dataclass(frozen=True, kw_only=True)
class SandboxContainerInventory:
    """Every running sandbox container the daemon reported, and whether it answered.

    `observed` is False exactly when the listing could not be taken. The
    container tuple is empty in that case too, so a consumer that ignored the
    flag would read a blinded sweep as a clean one.
    """

    containers: tuple[SandboxContainer, ...]
    observed: bool
    detail: str


@dataclass(frozen=True, kw_only=True)
class SandboxContainerPort:
    """The Docker CLI face the sandbox-container sweep acts through.

    `docker_host` is the daemon every verb on this port is addressed to, as
    the Docker CLI spells one. It is rendered as the GLOBAL `--host` option
    ahead of the verb, which is the only position the CLI accepts it in.
    """

    runner: CommandRunner
    cwd: Path
    docker_host: str
    docker_bin: str = DOCKER_BIN

    def inventory(self) -> SandboxContainerInventory:
        """List the running `fabro-run-*` containers with their memory limits."""
        listed = self.runner.run(
            argv=self._argv(
                verb="ps",
                arguments=[
                    "--filter",
                    f"name={SANDBOX_CONTAINER_NAME_PREFIX}",
                    "--format",
                    "{{.Names}}",
                ],
            ),
            cwd=self.cwd,
            timeout_seconds=_PS_TIMEOUT_SECONDS,
        )
        if listed.exit_code != 0:
            return SandboxContainerInventory(
                containers=(),
                observed=False,
                detail=f"docker ps exited {listed.exit_code}",
            )
        names = _container_names(stdout=listed.stdout)
        limits = self._memory_limits(names=names)
        return SandboxContainerInventory(
            containers=tuple(
                SandboxContainer(
                    name=name,
                    run_id=container_run_id(name=name),
                    memory_limit_bytes=limits.get(name),
                )
                for name in names
            ),
            observed=True,
            detail=f"{len(names)} running sandbox container(s) observed",
        )

    def remove(self, *, name: str) -> CommandResult:
        """Stop and remove one container, which `docker rm -f` does as one act."""
        return self.runner.run(
            argv=self._argv(verb="rm", arguments=["-f", name]),
            cwd=self.cwd,
            timeout_seconds=_REMOVE_TIMEOUT_SECONDS,
        )

    def _memory_limits(self, *, names: tuple[str, ...]) -> dict[str, int]:
        if not names:
            return {}
        inspected = self.runner.run(
            argv=self._argv(verb="inspect", arguments=["--format", _INSPECT_FORMAT, *names]),
            cwd=self.cwd,
            timeout_seconds=_INSPECT_TIMEOUT_SECONDS,
        )
        if inspected.exit_code != 0:
            return {}
        return _memory_limits_from_inspect(stdout=inspected.stdout)

    def _argv(self, *, verb: str, arguments: list[str]) -> list[str]:
        return [self.docker_bin, _HOST_OPTION, self.docker_host, verb, *arguments]


def _container_names(*, stdout: str) -> tuple[str, ...]:
    # The prefix is re-checked rather than trusted to `--filter name=`, which
    # matches a substring anywhere in the name: a container merely MENTIONING
    # the prefix carries no run id and must not be graded as if it did.
    return tuple(
        stripped
        for line in stdout.splitlines()
        if (stripped := line.strip()).startswith(SANDBOX_CONTAINER_NAME_PREFIX)
    )


def _memory_limits_from_inspect(*, stdout: str) -> dict[str, int]:
    limits: dict[str, int] = {}
    for line in stdout.splitlines():
        name, _, raw_limit = line.partition(_INSPECT_FIELD_SEPARATOR)
        limit = _byte_count(text=raw_limit.strip())
        if limit is not None:
            limits[name.strip().removeprefix(_DOCKER_NAME_PREFIX)] = limit
    return limits


def _byte_count(*, text: str) -> int | None:
    # `<no value>` is what the template renders for a field it could not read,
    # and an unparseable limit is an ABSENT reading rather than a zero one.
    return int(text) if text.isdigit() else None
