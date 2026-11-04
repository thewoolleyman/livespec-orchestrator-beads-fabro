---
topic: sandbox-capabilities-mirror-records-measured-image
author: claude-opus-5-5
created_at: 2026-10-30T20:33:46Z
---

## Proposal: sandbox-capabilities-mirror-records-measured-image

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The committed dispatcher.sandbox_capabilities mirror records the sandbox image it was measured on, in a machine-readable key; a mismatch with the resolved image is reported as a stale-mirror configuration mismatch, a missing or unestablishable image as unverifiable, a repository check compares them, and a catalog launch is unverifiable.

### Motivation

Work item bd-ib-o23n2x (filed under coordinator R500) found that the mirror is trusted after its image moves; a fleet survey on 2026-10-21 found eight lagging repositories. The coordinator regroom of 2026-10-30, under the maintainer's delegation, found no ratified clause for the key, the findings or the check, so all four Definition-of-Done assertions lack a governing heading. The proposal extends the Sandbox capabilities paragraph of Self-contained plugin dispatch rather than adding a heading.

### Proposed Changes

In SPECIFICATION/contracts.md, in the Sandbox capabilities paragraph, after the sentence ending "the journaled mismatch is how a violation is found.", add:

The committed array MUST be accompanied by the committed key `dispatcher.sandbox_capabilities_measured_image`, a string naming the sandbox image whose published capability file the array was measured from, in the form the image source resolves it (an image reference, or its digest). The key is read only beside an array, and it is not API-configurable, for the reason the array is not. The mirror tracks the image the committed configuration resolves for a dispatch that names no catalog environment, by the resolution §"Sandbox image source" and §"Sandbox image enumeration" define: `dispatcher.fabro_sandbox_image` when set, else the repository's own committed `implement-work-item` workflow pin, else the pin of the executing build's bundled workflow. It never tracks a catalog environment. When the image a dispatch resolves differs from the recorded measured image, the filing, groom and approve displays and every host taking of the Definition-of-Done judgement MUST report a STALE-MIRROR configuration mismatch that names both images. When the repository records no measured image, or the recorded or resolved image cannot be established, they MUST report an UNVERIFIABLE-MIRROR configuration mismatch that names its cause, and MUST NOT treat the array as verified. A dispatch whose resolved factory declares a catalog environment launches an image no committed file can name, so its comparison is not made: it is reported as UNVERIFIABLE-MIRROR with the cause `catalog_environment` and the environment id, and is never reported as stale. A stale-mirror or unverifiable-mirror report is a configuration mismatch in the sense above: it is not a finding against the item, it MUST NOT fail the `dod_gate` node or refuse an admission or a dispatch, the Dispatcher MUST journal it, and the grading set remains the committed array alone. The repository check `check-sandbox-capabilities-measured-image` MUST fail, naming both images, when a committed array's recorded measured image differs from the image the committed configuration resolves by that same resolution; a repository that records no measured image, and a resolution that is a catalog environment, pass the check with the unverifiable cause reported. A scenario in `scenarios.md` titled "A mirror records the sandbox image it was measured on" exercises these sentences.

In SPECIFICATION/scenarios.md add one scenario (numbered at revise), titled "A mirror records the sandbox image it was measured on", with this body:

```gherkin
Feature: The capability mirror records the sandbox image it was measured on
  Scenario: A mirror measured on an older image is reported stale and the check fails
    Given a repository whose committed dispatcher.sandbox_capabilities_measured_image names image A
    And a committed configuration whose dispatcher.fabro_sandbox_image resolves to image B
    When the filing display and the host-side Definition-of-Done judgement read the mirror
    Then each reports a stale-mirror configuration mismatch naming image A and image B
    And the Dispatcher journals the mismatch and neither refuses the admission nor fails the dod_gate node
    And the repository check check-sandbox-capabilities-measured-image fails naming image A and image B
  Scenario: A mirror that records no measured image is reported unverifiable
    Given a repository with a committed dispatcher.sandbox_capabilities array and no measured-image key
    When the approve display reads the mirror
    Then it reports an unverifiable-mirror configuration mismatch with the cause no-measured-image
    And the grading set is still the committed array alone
  Scenario: A catalog launch is unverifiable and never stale
    Given a factory declaring catalog environment livespec-ci and a committed measured image that differs from the catalog's image
    When a dispatch to that factory is judged
    Then the report is an unverifiable-mirror mismatch with the cause catalog_environment naming livespec-ci
    And no stale-mirror mismatch is reported
```
