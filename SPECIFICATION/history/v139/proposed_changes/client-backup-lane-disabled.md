---
topic: client-backup-lane-disabled
author: claude-opus-5-5
created_at: 2026-10-15T04:32:14Z
---

## Proposal: The tenant's client backup lane is disabled in its committed beads config

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a 'Client backup lane disabled.' bullet to contracts.md section 'Beads connection model': this repository's committed `.beads/config.yaml` MUST set `backup.enabled: false` with a comment naming the hourly server-side backup, the plugin MUST NOT seek the tenant privilege the client lane would need, and a `bd` call through the plugin MUST NOT print an `auto-backup failed` warning.

### Motivation

Plan dolt-server-failures (epic bd-ib-etfwwx), Definition of Done assertion 5, carrier bd-ib-rxf. dolt-server spec v023 (PR thewoolleyman/dolt-server#121) now requires every Beads tenant served by the shared server to commit `backup.enabled: false`, because the hourly server-side DOLT_BACKUP('sync','s3') is the tenant's backup and tenant accounts deliberately lack the global privilege a client backup registration needs. This repository's connection model is the authoritative record of how the plugin reaches its tenant, and it says nothing about the client backup lane, so bd-ib-rxf has no governing clause here. Measured: every `bd` write and read from this repository prints `Warning: auto-backup failed: register backup remote: add backup backup_export: Error 1105 (HY000): command denied to user 'livespec-orch-beads-fabro'@'%'`, which has repeatedly been read as a backup outage (bd-ib-rxf comments 2026-07 to 2026-08) while the central hourly sync reported every tenant synced. The August 2026 corrections on bd-ib-rxf rejected widening the tenant grant. Homelab PR #177 verified the key by an on/off/on experiment.

### Proposed Changes

In `SPECIFICATION/contracts.md` section "Beads connection model", insert this bullet immediately after the bullet that begins "**`dolt.auto-start: false`; auto-commit OFF.**":

- **Client backup lane disabled.** The repository's committed `.beads/config.yaml` MUST set `backup.enabled: false`, with a comment stating that the tenant is backed up server-side every hour by `dolt-backup.service` through `DOLT_BACKUP('sync','s3')`. Without the key, `bd` auto-enables a client backup lane whenever the repository has a git remote and tries to register a `backup_export` remote, which the shared dolt-server denies to the DB-scoped tenant user (Error 1105) by design. The plugin MUST NOT seek, require or document a tenant grant that would let that registration succeed. A `bd` call made through the plugin from the repository root MUST NOT print an `auto-backup failed` warning. Scenario 181 in `scenarios.md` exercises this bullet.

## Proposal: Scenario 181: a ledger write from this repository prints no auto-backup warning

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Add Scenario 181, a Gherkin block exercising the client-backup bullet: with the key committed, a `bd` write from the repository root prints no `auto-backup failed` warning and the next hourly central backup still reports every tenant synced.

### Motivation

The authoring discipline requires load-bearing behaviour to carry a clause and a scenario. The bullet above introduces an observable behaviour on stderr and in the central backup report. Scenarios 178 and 179 are ratified, and Scenario 180 is reserved by the pending proposal sandbox-path-protection, so this proposal takes 181.

### Proposed Changes

Append the following after the last scenario block in `SPECIFICATION/scenarios.md`. The revise pass MUST co-edit `tests/heading-coverage.json` with a TODO row for this heading owned by work-item bd-ib-rxf, and `tests/heading-coverage-debt.json` with the matching register row (first_seen set to the revision commit's UTC date), in the same change. If the revise pass finds 181 taken, it takes the next free number and updates the contracts.md cross-reference and both coverage rows to match.

## Scenario 181 — A ledger write from this repository prints no auto-backup warning

```gherkin
Feature: The tenant's client backup lane stays disabled
  As an operator reading the output of a ledger call
  I want no auto-backup failure warning from a lane the shared server will always refuse
  So that a warning about backups means a real backup problem

  Scenario: A ledger write with the key committed
    Given this repository's committed .beads/config.yaml sets backup.enabled: false
    And the repository has a git remote
    When a bd write runs from the repository root under the credential wrapper
    Then its stderr carries no auto-backup failed warning
    And the next hourly dolt-backup.service run still reports every tenant synced
```

The scenario's Then lines are observed outcomes; the normative MUST NOT remains in the contracts.md bullet.
