---
topic: sandbox-image-source
author: claude-opus-5-5
created_at: 2026-10-11T22:06:06Z
---

## Proposal: The catalog environment is the one source of the sandbox image when a dispatch names one

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A dispatch that names a factory catalog environment MUST launch its sandbox from the image that environment declares, and the Dispatcher launch overlay MUST leave that image unchanged; dispatcher.fabro_sandbox_image applies only to a dispatch that names no catalog environment; the dispatch journal records which source supplied the image. Adds Scenario 169.

### Motivation

Measured 2026-10-11 on hp-candidate run 01M4PBFW4MP8 (work-item bd-ib-o6aeji): the run declared catalog environment livespec-ci, whose image is python-agent-v1.93.5, and inspect reported run_spec.settings.run.environment.image and sandbox.plan.image at v1.93.5, but the started container (sandbox.instance.image) ran python-agent-v1.92.0, the value of dispatcher.fabro_sandbox_image, because the launch overlay rewrites the image. The plan and the running container therefore name different images, and a proof reading the plan reports an image that did not run. No section of the specification states which source wins, so work-item bd-ib-jy7fuh has no governing heading to reference.

### Proposed Changes

In SPECIFICATION/contracts.md, at the end of section "Dispatcher policy settings", add a subsection:

### Sandbox image source

A dispatch whose resolved factory declares a catalog environment (the factory's `environment` value under `dispatcher.factories`) MUST launch its sandbox from the image that catalog environment declares on the factory server. The Dispatcher launch overlay MUST NOT substitute `dispatcher.fabro_sandbox_image` for that image. A dispatch whose resolved factory declares no catalog environment MUST launch from `dispatcher.fabro_sandbox_image` when that key is set. The dispatch journal MUST record, for each launch, which source supplied the sandbox image: `catalog_environment` naming the environment id, or `dispatcher.fabro_sandbox_image`. Scenario 169 in `scenarios.md` exercises this subsection.

In SPECIFICATION/scenarios.md, append:

## Scenario 169 — A dispatch naming a catalog environment runs the catalog's image, and the journal names the image source

```gherkin
Feature: Sandbox image source

  Scenario: the catalog environment's image is the image the container runs
    Given a factory declaring catalog environment livespec-ci whose image is image A
    And dispatcher.fabro_sandbox_image set to image B
    When the Dispatcher launches a dispatch to that factory
    Then the launch carries image A
    And the dispatch journal records the image source catalog_environment livespec-ci

  Scenario: a factory with no catalog environment uses the committed image
    Given a factory declaring no catalog environment
    And dispatcher.fabro_sandbox_image set to image B
    When the Dispatcher launches a dispatch to that factory
    Then the launch carries image B
    And the dispatch journal records the image source dispatcher.fabro_sandbox_image
```

The same change MUST add a tests/heading-coverage.json entry for the Scenario 169 heading with test TODO and work_item bd-ib-jy7fuh.
