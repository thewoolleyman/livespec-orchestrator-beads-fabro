---
proposal: host-dispatch-cap.md
decision: accept
revised_at: 2026-07-24T08:03:59Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Maintainer-directed demotion of the interim binary admission mutex (brief-027, 2026-07-24, autonomous-overnight ruling): parallel throughput is the priority; bd-ib-tyxzhv proved no contended host resource exists at 2x (engine + sandbox + live-agent layers). The new committed dispatcher.host_dispatch_cap key (positive integer, default 2, no per-item override) is the durable spec commitment for the counting successor. Independent adversarial review returned NO-BLOCKERS (dispositions recorded in the track supervisor journal).

## Resulting Changes

- contracts.md
- scenarios.md
- spec.md
- ../tests/heading-coverage.json
