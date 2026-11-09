"""Read how a run's Kubernetes sandbox container terminated, before it is collected.

`SPECIFICATION/contracts.md` section "Provider-limit permanence and root-cause
surfacing" -> "A sandbox killed for memory is named." (`bd-ib-jnstxo`). The
evidence is the SANDBOX PROVIDER's own report: the pod's container termination
reason `OOMKilled`, and the memory limit the pod declares. The failure text is
NOT evidence. When the kernel's memory-cgroup killer takes the whole container,
the stage's next sandbox exec is refused with an API 500 that the engine records
as `transient_infra`, and that same sentence is what a genuine connection
failure carries; only the container's termination tells the two apart.

A POD IS ATTRIBUTED TO A RUN BY ITS NAME OR A LABEL VALUE carrying the run id
(lower-cased, because a Kubernetes object name cannot carry upper case), never
by position. A run whose pod is not listed -- already collected, or never
created -- is UNOBSERVABLE, not "not OOM-killed": absence of the pod says
nothing about how it ended.

EVERY UNREADABLE ARM IS REPORTED AS UNOBSERVABLE: a `kubectl` that is absent or
refuses, a listing that does not parse, and a run with no listed pod. None of
them may be read as a clean "no OOM kill", because that is the one answer that
would let an OOM-killed run keep its transient classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail
from livespec_orchestrator_beads_fabro.commands._fabro_resource_exhaustion import (
    SANDBOX_OOM_KILLED,
    ResourceExhaustion,
    SandboxTermination,
    sandbox_termination_statement,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "PERMANENT_CATEGORY",
    "memory_quantity_bytes",
    "oom_reclassified_failure",
    "permanent_failure_signature",
    "read_sandbox_termination",
]

KUBECTL_BIN = "kubectl"
_KUBECTL_TIMEOUT_SECONDS = 60.0
_OOM_KILLED_REASON = "OOMKilled"
PERMANENT_CATEGORY = "deterministic"
_TRANSIENT_SIGNATURE_SEGMENT = "|transient_infra|"

# The Kubernetes resource-quantity suffixes a memory limit is spelled with.
_QUANTITY_RE = re.compile(r"^(\d+)(Ki|Mi|Gi|Ti|k|M|G|T)?$")
_QUANTITY_FACTORS: dict[str, int] = {
    "": 1,
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "k": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
}


@dataclass(frozen=True, kw_only=True)
class _Container:
    name: str
    oom_killed: bool
    memory_limit_bytes: int | None


def memory_quantity_bytes(*, text: str) -> int | None:
    """A Kubernetes memory quantity in bytes, or None for a spelling not recognised."""
    match = _QUANTITY_RE.match(text.strip())
    if match is None:
        return None
    return int(match.group(1)) * _QUANTITY_FACTORS[match.group(2) or ""]


def read_sandbox_termination(
    *,
    runner: CommandRunner,
    cwd: Path,
    run_id: str,
) -> SandboxTermination:
    """Ask the cluster how this run's sandbox container ended."""
    listed = runner.run(
        argv=[KUBECTL_BIN, "get", "pods", "--all-namespaces", "-o", "json"],
        cwd=cwd,
        timeout_seconds=_KUBECTL_TIMEOUT_SECONDS,
    )
    if listed.exit_code != 0:
        return _unobservable(run_id=run_id, detail=f"kubectl get pods exited {listed.exit_code}")
    pods = _run_pods(run_id=run_id, stdout=listed.stdout)
    if pods is None:
        return _unobservable(run_id=run_id, detail="the pod listing could not be parsed")
    if not pods:
        return _unobservable(run_id=run_id, detail="no sandbox pod for the run is listed")
    containers = [container for pod in pods for container in _containers(pod=pod)]
    killed = next((container for container in containers if container.oom_killed), None)
    return SandboxTermination(
        run_id=run_id,
        observed=True,
        oom_killed=killed is not None,
        memory_limit_bytes=None if killed is None else killed.memory_limit_bytes,
        detail=f"{len(pods)} sandbox pod(s) read",
    )


def oom_reclassified_failure(
    *,
    failure: FabroFailureDetail | None,
    termination: SandboxTermination,
) -> FabroFailureDetail | None:
    """The failure an OOM-killed sandbox leaves, permanent in category and signature.

    The typed provider-limit state is left exactly as it arrived: a sandbox
    killed for memory is not a spend ceiling, and the admission gate must not
    read it as one. A reading that shows no OOM kill returns the failure as it
    arrived, and the CONTROL clause keeps its category.
    """
    statement = sandbox_termination_statement(termination=termination)
    if not termination.observed or not termination.oom_killed or statement is None:
        return failure
    exhaustion = ResourceExhaustion(
        kind=SANDBOX_OOM_KILLED,
        run_id=termination.run_id,
        memory_limit_bytes=termination.memory_limit_bytes,
    )
    if failure is None:
        return FabroFailureDetail(
            cause=statement,
            category=PERMANENT_CATEGORY,
            signature=None,
            resource_exhaustion=exhaustion,
        )
    return replace(
        failure,
        category=PERMANENT_CATEGORY,
        signature=permanent_failure_signature(signature=failure.signature),
        resource_exhaustion=exhaustion,
    )


def permanent_failure_signature(*, signature: str | None) -> str | None:
    """The signature with its transient category segment rewritten to the permanent one."""
    if signature is None:
        return None
    return signature.replace(_TRANSIENT_SIGNATURE_SEGMENT, f"|{PERMANENT_CATEGORY}|")


def _unobservable(*, run_id: str, detail: str) -> SandboxTermination:
    return SandboxTermination(
        run_id=run_id, observed=False, oom_killed=False, memory_limit_bytes=None, detail=detail
    )


def _run_pods(*, run_id: str, stdout: str) -> list[dict[str, Any]] | None:
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    items: object = cast("dict[str, Any]", parsed).get("items")
    if not isinstance(items, list):
        return None
    needle = run_id.lower()
    return [
        pod
        for item in cast("list[object]", items)
        if isinstance(item, dict)
        and _names_run(pod=(pod := cast("dict[str, Any]", item)), needle=needle)
    ]


def _names_run(*, pod: dict[str, Any], needle: str) -> bool:
    metadata: object = pod.get("metadata")
    if not isinstance(metadata, dict):
        return False
    fields = cast("dict[str, Any]", metadata)
    labels: object = fields.get("labels")
    values = [fields.get("name")]
    if isinstance(labels, dict):
        values.extend(cast("dict[str, object]", labels).values())
    return any(isinstance(value, str) and needle in value.lower() for value in values)


def _containers(*, pod: dict[str, Any]) -> list[_Container]:
    limits = dict(_declared_limits(pod=pod))
    statuses: object = _mapping(value=pod.get("status")).get("containerStatuses")
    if not isinstance(statuses, list):
        return []
    found: list[_Container] = []
    for entry in cast("list[object]", statuses):
        status = _mapping(value=entry)
        name = status.get("name")
        if not isinstance(name, str):
            continue
        found.append(
            _Container(
                name=name,
                oom_killed=any(
                    _mapping(value=_mapping(value=status.get(key)).get("terminated")).get("reason")
                    == _OOM_KILLED_REASON
                    for key in ("state", "lastState")
                ),
                memory_limit_bytes=limits.get(name),
            )
        )
    return found


def _declared_limits(*, pod: dict[str, Any]) -> list[tuple[str, int]]:
    declared: object = _mapping(value=pod.get("spec")).get("containers")
    if not isinstance(declared, list):
        return []
    limits: list[tuple[str, int]] = []
    for entry in cast("list[object]", declared):
        container = _mapping(value=entry)
        name = container.get("name")
        memory = _mapping(value=_mapping(value=container.get("resources")).get("limits")).get(
            "memory"
        )
        parsed = memory_quantity_bytes(text=memory) if isinstance(memory, str) else None
        if isinstance(name, str) and parsed is not None:
            limits.append((name, parsed))
    return limits


def _mapping(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}
