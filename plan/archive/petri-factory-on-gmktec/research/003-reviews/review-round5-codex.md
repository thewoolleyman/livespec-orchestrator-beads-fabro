VERDICT: NO BLOCKERS

- SHOULD-FIX — `SPECIFICATION/proposed_changes/factory-addresses-from-a-gitops-registry.md:182`: Explicitly give this registry object a valid `server`. Otherwise, refusal for a missing server can satisfy the scenario without testing invalid `docker_host`. Add whitespace-only and non-string cases to cover the validation rule fully.
- NIT — `SPECIFICATION/proposed_changes/factory-addresses-from-a-gitops-registry.md:210`: Replace “exactly as a committed entry” with observable assertions: the sweep reports the named factory as unobserved and never opens a daemon connection. That matches `_dispatcher_reconcile_runs_containers.py:161`.

The additions preserve round 3’s approved behavior. Optional daemon resolution, conflicting-address refusal, and the committed-entry restriction are consistent with the code. Stricter validation applies specifically to registry values, preserving literal-entry compatibility.

The reviewed worktree’s `SPECIFICATION/contracts.md` contains no existing `docker_host` text; daemon semantics were verified against `_config.py`, the container sweep, and `.livespec.jsonc`.

REVIEW-COMPLETE
