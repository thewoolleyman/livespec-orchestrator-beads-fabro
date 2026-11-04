---
topic: sandbox-test-parallelism-four
author: claude-opus-5-5
created_at: 2026-10-26T10:32:59Z
---

## Proposal: Factory sandboxes project four test workers

### Target specification files

- SPECIFICATION/contracts.md

### Summary

This repository projects LIVESPEC_TEST_PARALLELISM=4, the CPU limit of its 4-CPU factory sandboxes, instead of 2, because a measured four-worker gate fits the sandbox's memory with headroom.

### Motivation

Fleet coordinator ruling R25 (gitops-fleet-capacity-monitoring, 2026-10-26). The two-worker cap ended the memory-cgroup OOMs but cost wall time: bd-ib-od7v54 was cancelled at its 6 h budget after about 5 h in implement's Green amend, where each pre-commit per-file-coverage pass took about 20 minutes. Measured 2026-10-26 on the vmi host, a full `just check-per-file-coverage` run at 4 workers inside a memory-accounted cgroup scope peaked at 2748 MiB (memory.peak), with each xdist worker's peak resident set at or below 467 MiB. That is 36% of the sandbox's 7630 MiB and inside the coordinator's 80% bar of 6100 MiB. The clause already caps the value at the sandbox CPU limit, which is 4, so only its stated value changes.

### Proposed Changes

In SPECIFICATION/contracts.md, in the paragraph that begins 'The Dispatcher MUST project `LIVESPEC_TEST_PARALLELISM` into every dispatched sandbox's environment', replace the sentence 'This repository projects 2, for its 4-CPU factory sandboxes.' with: 'This repository projects 4, for its 4-CPU factory sandboxes. Four workers fit the sandbox's 7630 MiB memory limit: measured on 2026-10-26, a full per-file-coverage gate run at four workers peaked at 2748 MiB of cgroup memory, with no worker above 467 MiB resident.' Leave every other sentence of the paragraph unchanged.

