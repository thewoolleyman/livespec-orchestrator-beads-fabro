---
proposal: factory-sandbox-credential-capability-boundary.md
decision: accept
revised_at: 2026-07-20T22:45:14Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Accepted as proposed, after an independent adversarial review returned no blockers against current origin/master. The new constraints.md section codifies the maintainer's 2026-07-20 decision as a capability rule: a credential projected into the factory sandbox must not carry any capability that lets the unattended agent execute code on the host substrate or rewrite a gate validating the factory's own output, with GitHub `workflows` read-write as the rejected worked instance and automatic routing to the attended host session as the resolution. The co-edits repair the three statements that prescribed the opposite posture (contracts.md's App-installation-requirement sentence, Scenario 32's step, and the factory_safety sharp line that classified workflow edits as factory-safe), extend Scenario 48 with the precision-pinning refusal/admission pair, and add the heading-coverage entry for the one new H2 heading.

## Resulting Changes

- constraints.md
- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
