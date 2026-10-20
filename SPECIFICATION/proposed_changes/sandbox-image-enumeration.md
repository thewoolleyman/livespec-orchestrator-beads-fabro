---
topic: sandbox-image-enumeration
author: claude:fabro-currency (session 5c3e43cb)
created_at: 2026-10-20T15:48:03Z
---

## Proposal: Sandbox image enumeration

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a governing clause, a new subsection `### Sandbox image enumeration` under `## Dispatcher policy settings` placed directly after `### Sandbox image source`, plus one new scenario, for a read-only `dispatcher.py sandbox-images` subcommand. The command enumerates every sandbox image a dispatch to a named factory can resolve at the moment it runs. It answers through the dispatch's own resolution code, across a defined repository set and a defined executing-build set, and it reports an unreadable source and exits non-zero. It writes nothing, starts no run and pulls no image.

### Motivation

Work-item bd-ib-nqmltq (plan fabro-currency, epic bd-ib-6tcjfx; coordinator rulings R295 and R296, 2026-10-20) builds this primitive for the docker factory host image-warm timer of livespec-dev-tooling-dq3km7. That timer must warm every tag a dispatch to the host can pull, so that two first pulls of one new tag cannot race and kill each other's sandbox init (hold R286). The ratified precedence is split across `### Sandbox image source` (catalog environment, then `dispatcher.fabro_sandbox_image`) and the Target-local workflow paragraph of `## Self-contained plugin dispatch` (the target's own implement-work-item workflow, else the bundled workflow of the EXECUTING payload). Measured on vps on 2026-10-20 at about 10:40Z: 12 sandbox tags were reachable on hp, because a long-lived session or a dispatcher loop runs the build it started with, not the registered one. The dispatch journal cannot answer the question either, because it writes `sandbox_image` null on the committed-run-config arm. The first dispatch of bd-ib-nqmltq (hp run 01M5CNTW4R3B) ended partial. Its pre-dispatch Definition-of-Done preflight then found three ungoverned behaviours: which consumer repositories are enumerated, which builds count as executing, and what happens to an unreadable source. This proposal gives each a clause and a scenario the item can cite.

### Proposed Changes

In SPECIFICATION/contracts.md, directly after the subsection `### Sandbox image source` under `## Dispatcher policy settings`, add the subsection below. In SPECIFICATION/scenarios.md, append the scenario below after the last existing scenario, numbered with the next free scenario number at revise time (written here as Scenario 212); the assigned number MUST be used consistently in the contract text, the scenario heading and both coverage rows. In the same change, `tests/heading-coverage.json` MUST gain one row for the new scenario heading with `test` `TODO`, a non-empty `reason` naming this proposal, and `work_item` `bd-ib-nqmltq`, and `tests/heading-coverage-debt.json` MUST gain one owned row for the same heading naming bd-ib-nqmltq. No other heading changes.

Subsection text for contracts.md:

### Sandbox image enumeration

The Dispatcher MUST provide a read-only subcommand, `dispatcher.py sandbox-images --factory <name> [--repo <path>]... [--json]`, that enumerates every sandbox image a dispatch to the named factory can resolve at the moment the command runs. The command MUST NOT write a ledger record, a dispatch-journal row or any other file. It MUST NOT create a Fabro run, and it MUST NOT pull, build or tag an image.

**Repositories.** Without `--repo`, the command MUST enumerate every repository whose root is the `projectPath` of an install record of this plugin in the host's Claude Code install registry (`~/.claude/plugins/installed_plugins.json`). When one or more `--repo` arguments are given, it MUST enumerate exactly those repositories instead. A repository whose committed `dispatcher.factories` declares no entry of the named factory MUST be reported with source `factory_undeclared` and no image, and that report alone MUST NOT make the command exit non-zero.

**Executing builds.** The executing-build set is host-wide. It MUST consist of: the build named by each enumerated repository's registered install record; every plugin-cache build that holds an `.in_use` lease whose recorded process is alive; and the payload of every running Dispatcher process. A build whose only lease names a process that has exited MUST NOT be enumerated. A build reached by more than one route MUST be enumerated once.

**Entries.** For each enumerated repository, the command MUST report entries in the order a dispatch to that factory resolves its sandbox image. It MUST decide each one by calling the same resolution functions a dispatch calls, never a parallel copy:

1. When the factory's entry declares a catalog environment, one entry with source `catalog_environment`, that environment id, and no image of its own.
2. Otherwise, when the repository sets `dispatcher.fabro_sandbox_image`, one entry with that image and source `dispatcher.fabro_sandbox_image`.
3. Otherwise, when the repository commits its own `.fabro/workflows/implement-work-item/workflow.toml`, one entry with that file's `docker` pin, source `committed_run_config`, and the path of that file.
4. Otherwise, one entry per executing build, each with the `docker` pin of that build's bundled implement-work-item `workflow.toml`, source `bundled_run_config`, the build's identity, and the path of that file.

Each entry MUST name its repository. With `--json`, the command MUST print one JSON array holding every entry as an object.

**Unreadable sources.** When a repository's `.livespec.jsonc`, a committed workflow file or a bundled workflow file that an entry depends on cannot be read or parsed, that entry MUST be reported with source `unreadable` and the path that failed. The command MUST still report every other entry, and it MUST then exit non-zero.

Scenario text for scenarios.md:

## Scenario 212 — The sandbox-images command reports every image a dispatch to a factory can resolve, through the dispatch's own resolution, and changes nothing

```gherkin
Feature: Read-only sandbox image enumeration
  As the operator of a docker factory host's image-warm timer
  I want every sandbox image a dispatch to that factory can pull, from the dispatch's own resolution
  So that the host holds each tag before the first run that needs it

Scenario: A factory with a catalog environment reports the environment, not an image
  Given a repository whose dispatcher.factories entry for factory F declares a catalog environment E
  When dispatcher.py sandbox-images --factory F --repo <that repository> --json runs
  Then it prints one entry for that repository with source catalog_environment and environment E
  And that entry carries no image of its own

Scenario: A configured image wins over every workflow pin
  Given a repository that sets dispatcher.fabro_sandbox_image to image I and commits its own implement-work-item workflow.toml
  And factory F declares no catalog environment
  When the command runs for factory F and that repository
  Then it prints one entry for that repository with image I and source dispatcher.fabro_sandbox_image

Scenario: A committed workflow pin is reported with its path
  Given a repository with no configured image that commits its own implement-work-item workflow.toml pinning image J
  When the command runs for factory F and that repository
  Then it prints one entry with image J, source committed_run_config and the path of that workflow.toml

Scenario: The bundled pin is reported once per live executing build
  Given a repository with neither a configured image nor its own workflow
  And its registered install is build B1, a live process holds an .in_use lease on build B2, and a lease on build B3 names a process that has exited
  When the command runs for factory F and that repository
  Then it prints one bundled_run_config entry for B1 and one for B2, each with that build's bundled docker pin
  And it prints no entry for B3

Scenario: An unreadable source is reported and fails the command after every other entry
  Given two repositories, one of which has a .livespec.jsonc that does not parse
  When the command runs for factory F with both repositories
  Then it prints an entry with source unreadable and that file's path
  And it prints the other repository's entries in full
  And it exits non-zero

Scenario: The command changes nothing
  Given any repositories and factory F
  When the command runs
  Then no ledger record, dispatch-journal row or Fabro run is created
  And no image is pulled, built or tagged
```
