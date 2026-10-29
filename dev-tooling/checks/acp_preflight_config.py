# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""acp_preflight_config — the committed ACP chain configuration must resolve.

`SPECIFICATION/contracts.md` section "Agent and model catalogs" and Scenario
129 ratify that a mixed, unknown or unresolvable chain entry refuses BEFORE
claim. That refusal used to surface only when a real dispatch was admitted:
the Codex-first routing rollout copied this repository's `acp_nodes` block
into 13 fleet repositories, which declared a Claude fallback model only this
repository's `dispatcher.model_catalog` knew, and every one of the 13 then
refused every dispatch at the ACP preflight while each pre-commit hook,
pre-push hook and CI run on the copying change passed. This check runs the
SAME evaluation at commit time.

THE EVALUATION IS THE DISPATCHER'S OWN, NOT A SECOND READING. It calls
`resolve_acp_preflight` and fails on a configuration refusal -- the verdict's
`refusal` -- printing that text verbatim. A parallel validator would be a
second reading of the same configuration that could not be proven to agree
with the one dispatch uses, and the disagreement would be silent.

IT SUPPLIES NOTHING ELSE, ON PURPOSE. No credential probe, no session-headroom
policy, no factory reader, no confirmation turn and no journal (`journal_path`
is `None`, so no availability hold is read). The verdict is therefore a pure
function of the committed `.livespec.jsonc` and the committed workflow files:
deterministic, and computable on a host with no network. An availability wait
or a live hold is not a configuration defect and must not turn a commit red,
which is why `exhausted` is not consulted -- only `refusal` is.

Usage: `acp_preflight_config.py [repo-root]`; the root defaults to this
repository, and the argument exists so the check can be pointed at a fixture.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
_SCRIPTS_VENDOR = _SCRIPTS / "_vendor"
for _path in (_SCRIPTS, _SCRIPTS_VENDOR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script
# (per the `no_write_direct` ban on direct `sys.stderr.write`). It is not
# vendored in this repo's own tree, so it is imported from the installed
# `livespec_dev_tooling` package's vendored copy.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
# APPEND, never insert at the front: that `_vendor` also carries a PARTIAL
# `livespec_runtime`, and putting it ahead of this repo's own `_vendor` shadows
# the full copy every plugin module imports (livespec-dev-tooling-8o8e.24 is
# the two-copies class).
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

import structlog  # noqa: E402

# `commands.dispatcher` has to be imported before the preflight module, or the
# import cycle between the two fails.
_ = importlib.import_module("livespec_orchestrator_beads_fabro.commands.dispatcher")
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (  # noqa: E402
    resolve_acp_preflight,
)

__all__: list[str] = ["main", "resolve_acp_preflight"]


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("acp_preflight_config")
    arguments = sys.argv[1:]
    repo = Path(arguments[0]) if arguments else _REPO_ROOT
    verdict = resolve_acp_preflight(
        repo=repo,
        journal_path=None,
        now_iso=datetime.now(timezone.utc).isoformat(),
    )
    if verdict.refusal is None:
        return 0
    log.error("acp preflight configuration refusal", repo=str(repo), refusal=verdict.refusal)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
