## The maintainer's statement of what done means

Do not stop and ask for any human confirmation unless you are truly blocked, work atonomusly, make the plan, test it, build it (with factory if possible), and roll it out.

## Definition of Done assertions derived from that statement

- A CLI invocation from the normally installed released orchestrator completes its deferred packaged-code, asset and helper work after native Codex plugin removal deletes its original isolated cache, while retaining one unchanged release throughout.
- After normal native Codex plugin reinstall in that isolated home, a fresh orchestrator CLI invocation executes the installed release successfully while any earlier invocation retains its own complete payload until completion.

# Dispatcher payload lifetime after native plugin cache eviction

This is a bounded shared-tooling repair discovered while executing overseer-herdr-rewrite (overseer-uzvcbn), not additional Herdr product behavior. The quoted user statement above is the original authorization for autonomous testing and rollout; the cache-lifetime assertions are session-derived from the observed blocker and the coordinator's explicit repair delegation, not a purported verbatim cache requirement from the maintainer.

## Observed incident and prior art

On 2026-10-06, host PID 1894716 still ran installed Codex cache 0.173.0 scripts/bin/drive.py for overseer-ssjzmo / hp run 01M47ANKZS2CEED4H6FRH8KW5W, while its cache directory had disappeared and only 0.173.3 remained. The process was alive: a later import failure for this run was a prediction, not an observed verdict. Orchestrator item bd-ib-3ftj records the identical real _dispatcher_cost_wave ModuleNotFoundError after older Codex cache eviction in August; its acceptance concerns currency identification, not payload lifetime. bd-ib-fhjqbv concerns startup completeness only. All-status surveys in orchestrator, dev-tooling and Codex-driver found no active lifetime repair. Dev-tooling p2ttls/s1ic concern concurrent Claude provisioning and incomplete extracts. Closed Codex-driver ihglyp aliases separately invoked hook paths to newer builds; that would mix builds in a partially imported Dispatcher and is not this fix.

## Contract and bounded design

SPECIFICATION/contracts.md, Self-contained plugin dispatch, and Scenario 54 require released packaged execution with no orchestrator checkout dependency, no running-Dispatcher code writes or artifact replacement, and preserved candidate canary/restart-due behavior. The correction belongs to the packaged launcher BEFORE Dispatcher application imports or claims work: provision one complete, validated, same-release execution payload outside harness-managed cache, then launch from it. Keep scripts, vendored dependencies, workflow, prompt assets and helper entry points together. Preserve selected-release provenance separately from runtime location. The running Dispatcher remains read-only and never changes build. A new invocation resolves the normal installed release afresh. If implementation requires changing those specification requirements, stop and report; do not smuggle a second execution mode or reinterpret an exception.

Do not repair/restore/pin/alias shared evicted caches, redirect imports to newer payloads, preload just one failing module, suppress import failures, alter ambient-currency policy, or modify another live dispatch. No changes to overseer behavior or Herdr S2/S3/S4 are carried here. No factory-authored SPECIFICATION changes.

## Verification and release

Author and execute one genuine behavioral regression against existing public launcher behavior BEFORE any product change. It must synchronize a real child process, remove only a disposable copied installation after startup, then demand deferred operation/assets/helper execution; current behavior must fail an assertion, not test collection. Preserve exact Red bytes through Green amend. Distinct fixture releases can prove build isolation without waiting for a future release. Factory proof must demonstrate shipped launcher behavior on terminal/subprocess/filesystem surfaces, not merely cite passing tests.

After PR merge and release, install the release through normal Codex marketplace/install commands into a genuinely isolated Codex home. Capture a real CLI invocation surviving native plugin removal, then normal reinstall and a fresh CLI invocation; do not depend on a future published release. Capture actual process identity, source-cache disappearance, retained execution paths, release/content provenance and meaningful CLI results. A separately started agent must replay host and plan proof under its own identity. Keep the epic live until that verification and independent completeness review exist.
