---
topic: the-named-build-adopt-writes-no-other-record
author: claude-opus-5-5
created_at: 2026-11-10T02:39:21Z
---

## Proposal: The named-build adopt writes no other clone's install record; it cannot stop the host's own Claude Code from moving one

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Orchestrator spec v337 says of the named-build adopt that "another clone's install MUST NOT move while it runs". No adopt step can honour that. Every clone and project on a host shares ONE `~/.claude/plugins/installed_plugins.json`, and every `claude plugin` install, update or uninstall rewrites that file whole, under no lock an adopt step can share. A session-start refresh in any project counts, as does an operator command. The rewrite can move another clone's record, or revert one, while an adopt runs. This proposal narrows the clause to what the adopt step controls: it writes no install record but the named clone's. The proposal also names the residual and its recovery, and points the clause at livespec-dev-tooling's ratified tag adopt instead of the pending proposal it cites today.

### Motivation

On 2026-11-10 at about 02:0xZ, legacy-coordinator-agent routed this residual to the gmktec-factory-placement seat. That seat owns the canary design (livespec-dev-tooling-zpqvnr, plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz) and the text that conflicts with it. The coordinator asked for one orchestrator propose-change that either (a) narrows v337 to what is enforceable or (b) specifies a per-clone atomic install-record write under a lock that preserves other clones' entries. Its fleet scope is every project and clone on every host that shares one `installed_plugins.json`. It is linked to livespec-dev-tooling-gpo5cp, which requires SessionStart reconcilers to leave an orchestrator install record unchanged, the same class of hazard.

This proposal recommends (a), because (b) cannot be proven:

- The file's writer is Claude Code itself. `claude plugin install`, `update` and `uninstall` read the file, change their own record and write the whole file back. They take no lock that livespec-dev-tooling, or anything else outside Claude Code, can share.
- A lock held by the adopt step therefore serializes only other adopt steps. livespec-dev-tooling v176 already ratifies exactly that as its **Adoption lock.** It cannot stop a session start in another project from rewriting the file in the same second.
- Measured on this host on 2026-11-10: `installed_plugins.json` carries 26 orchestrator project-scope records. It is rewritten by the SessionStart `ensure-plugins` reconcile of every livespec project, and by the `claude plugin update -s project` hooks of homelab (`.claude/hooks/ensure_plugins.py`), resume (`.claude/hooks/ensure-plugins.ts`), openbrain and livespec-tdd-proof, which no livespec-dev-tooling release reaches.
- livespec-dev-tooling v176's tag adopt keeps the window as small as it can. It re-reads the file immediately before an atomic rename and re-applies its one change at most three times. It then names the residual that remains: a write landing between that last re-read and the rename can be lost, and that write may be another clone's update. A clause the adopt step cannot satisfy turns every canary into a violation of the spec by an event no operator can see, and it gives nobody a remedy.

The narrowed clause keeps the substance v337 needs:
- The adopt step itself never writes another clone's record.
- The step checks its own record after a settle period.
- A reverted record of any clone is recovered by re-running the step that wrote it.

The canary still runs one clone at a time, and a sample whose install record does not name the tag under canary is already discarded rather than judged, so a revert during a canary cannot be mistaken for a canary result.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Self-contained plugin dispatch", paragraph "**The release channel.**":

1. Replace "installs that tag's build at project scope in that clone, and leaves the commit `release` names, the host's marketplace registration, and every other clone's install record unchanged when the adopt step ends; another clone's install MUST NOT move while it runs." with "installs that tag's build at project scope in that clone, and leaves the commit `release` names and the host's marketplace registration unchanged. The adopt step MUST NOT write any install record other than the named clone's. It cannot stop another writer from moving one: every clone and project on a host shares one `installed_plugins.json`, which every `claude plugin` install, update or uninstall rewrites whole under no lock the adopt step can share, so a concurrent write elsewhere on the host can move or revert another clone's record, or the named clone's, while the adopt step runs. The adopt step MUST therefore re-read the named clone's record after a settle period and fail when it no longer names the tag's commit, and a record that such a write reverted is recovered by re-running the step that wrote it."

2. Replace "livespec-dev-tooling's `just adopt-orchestrator-build <clone> <tag>`, in the tag form that repository's pending proposal a-canary-clone-adopts-a adds (owner work item livespec-dev-tooling-zpqvnr)." with "livespec-dev-tooling's `just adopt-orchestrator-build <clone> <tag>`, in the tag form that repository's specification v176 ratifies as **Tag adopt.** (owner work item livespec-dev-tooling-zpqvnr)."

No scenario changes: Scenario 331's "a canary clone adopts a release tag while the release branch keeps its commit" states the adopt step's own effect on clones A and B with no concurrent writer, and the narrowed clause keeps that outcome.
