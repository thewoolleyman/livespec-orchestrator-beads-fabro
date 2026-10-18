---
topic: factory-addresses-from-a-gitops-registry
author: claude-opus-5-5
created_at: 2026-10-15T06:36:00Z
---

## Proposal: Factory addresses resolved from a host registry

### Target specification files

- SPECIFICATION/contracts.md

### Summary

A dispatcher.factories entry MAY declare "registry": true instead of a server value; its server address is then resolved by factory name from a host-side registry file that the fleet's provisioning renders from its inventory. A registry entry carries the factory's server address and, optionally, its container-daemon address (docker_host). This repository's own committed entries MUST be registry-backed and carry neither form, fleet members' SHOULD be registry-backed, and other adopters keep the literal server form. An unresolvable registry-backed factory MUST be refused before claim and MUST NOT fall back to any other target. Every consumer of a factory address shares the one resolution while keeping its established failure behaviour, and a registry-backed entry counts as a remote factory wherever the Dispatcher classifies a target as remote. The recorded-pin fallback is unchanged and applies only when no explicit selection is made. Factory names SHOULD name instances, while dispatcher.default_factory alone carries which instance serves.

### Motivation

The maintainer ruled on 2026-10-15 (plan bd-ib-fyozyd, petri-factory-on-gmktec) that no committed factory entry may name a machine hostname, so that a factory is bound to a machine only in the gitops inventory, and the factory can move to gmktec-xubuntu now and onto Kubernetes later without repository changes. Measured: fifteen fleet repositories commit factory tables whose server values name hp-xubuntu or vps. A Tailscale Service cannot provide a machine-free name (only tagged devices host one, agents may not add tags, and tagging gmktec would remove it from the member SSH grant), and HTTPS through tailscale serve rules out DNS aliases. Today an entry with no server resolves to the ambient local Fabro target, so simply deleting server values would silently re-route dispatches; the refusal rule exists to close that. The naming rule and the recorded-pin note were agreed with the fabro-currency plan, which owns the cutover: 425 items in this tenant record the factory name hp, and a renamed factory re-routes their later dispatches to the default rather than refusing them.

Revision 3 (2026-10-18) also carries `docker_host`: this repository's committed `hp` entry names its machine through `docker_host` (`ssh://...@hp-xubuntu...`), which the reconcile pass's container sweep reads, so a registry-backed entry resolves that address from the registry too and a committed one carries neither form (finding from the livespec-dev-tooling companion proposal's review). Revision 2 (2026-10-18) answers an independent read-only review (gpt-6-astra, review text preserved under plan/petri-factory-on-gmktec/research/003-reviews/). It qualifies the recorded-pin fallback by the ratified selection order, makes the hostname-free rule normative for this repository, extends shared resolution to address-dependent classification (the run-turn telemetry export reads a literal server key today) and to the non-Dispatcher readers with their existing failure semantics, fixes the validation scope to the selected entry, and widens Scenario 182.

### Proposed Changes

Insert the following subsection into `contracts.md` §"Dispatcher policy settings", immediately after the subsection "### Sandbox image source" and before the next `## ` heading ("## Built-in ACP node defaults"):

```markdown
### Factory addresses resolved from a host registry

A `dispatcher.factories` entry MAY declare `"registry": true` in place of a
`server` value. The server address of such a REGISTRY-BACKED entry MUST be
resolved by the entry's own name from the factory registry: a JSON file whose
path is the value of `LIVESPEC_FABRO_FACTORY_REGISTRY` when that variable is set
and non-empty, and otherwise `/etc/livespec/fabro-factories.json`. The registry
is host state rendered by the fleet's provisioning from its inventory; no
committed file in a governed repository writes it. An entry that carries
`server` and no `registry` key keeps its existing meaning unchanged, and
`server` remains the supported form for an adopter repository outside the
livespec fleet.

Every committed `dispatcher.factories` entry in this repository's own
`.livespec.jsonc` MUST be registry-backed and MUST NOT carry a `server` or a
`docker_host` value.
A fleet member repository's committed entries SHOULD be registry-backed, so that
binding a factory to a machine is a change to the provisioning inventory alone.

Resolution reads only what the selected entry needs. The registry file MUST
parse as JSON whose top-level value is an object; within it, the value under the
selected factory's name MUST be an object whose `server` value is a string that
is non-empty after surrounding whitespace is removed. That object MAY carry a
`docker_host` string, spelled as the Docker CLI's `DOCKER_HOST`; when it does,
it is the registry-backed factory's container-daemon address, exactly as a
committed entry's `docker_host` is for an entry that carries `server`, and when
it does not, the factory declares no container-daemon address. A `docker_host`
value that is present but is not a string non-empty after trimming is refused
like an invalid `server`. Other entries in the registry are not validated by
that resolution and do not affect it.

The Dispatcher MUST refuse, before any claim, ledger write of any kind (status,
metadata or comment) or Fabro run creation, a dispatch whose resolved factory
is registry-backed when the registry file is absent or unreadable, does not
parse as JSON, has a top-level value that is not an object, has no entry for
that factory name, or gives that entry no valid `server` string. The refusal
MUST name the factory and the registry path it read. The Dispatcher MUST NOT
fall back to the ambient local Fabro target, to `dispatcher.default_factory`,
or to any other factory in that case. An entry declaring `"registry": true`
together with `server` or `docker_host` MUST be refused the same way, naming
the factory.

Every surface that turns a declared factory into an address MUST use this one
resolution, and every surface whose behaviour depends on whether a factory is
remote MUST treat a registry-backed entry as naming a server. That includes
dispatch and resume, the reconcile survey of declared factories, the liveness
question asked of each factory a journal names, the availability-evidence reads
of §"Factory-configurable ACP fallback priority", the run-turn telemetry
export's remote-factory classification, plan run liveness, the merge-hold
liveness guard, the run-event projection, and the needs-human valve
enrichment. A surface that cannot resolve a registry-backed factory MUST keep
the failure behaviour already ratified for an unreachable factory on that
surface: a survey or liveness read reports that factory as unobservable, naming
it, and MUST NOT skip it silently or treat it as holding no runs; the valve
enrichment costs the enrichment and never the valve. One unresolvable factory
MUST NOT prevent the reconcile survey from observing the other declared
factories. A resolved registry-backed dispatch MUST record the resolved server
address in the item's dispatch-factory record exactly as a `server` entry does.
A factory's per-name settings — its dev token, its secret-channel declaration,
its `bin` and its `environment` — stay keyed by the factory name, unchanged.

The registry refusal applies only to resolving a DECLARED, registry-backed
entry. It does not change the factory selection order: an explicit
`--factory` is taken first, then `LIVESPEC_FABRO_FACTORY` when it is set and
non-empty; then the
item's recorded factory; then `dispatcher.default_factory`. A recorded factory
name that `dispatcher.factories` no longer declares keeps its existing
treatment: when no explicit selection is made it is ignored and the dispatch
falls back to `dispatcher.default_factory`, so renaming a factory re-routes the
later unpinned dispatches of every item that recorded the old name onto the
default factory. A `dispatcher.default_factory` that names no declared entry
keeps its existing treatment as well; this clause does not govern it.

A factory name SHOULD name the Fabro server instance it addresses and SHOULD
stay the same for that instance's whole life. Which instance serves a
repository by default MUST be carried only by `dispatcher.default_factory`, so
that moving the default from one instance to another changes that one key and
renames nothing.
```

## Proposal: Scenario 182: registry-backed factory resolution and refusal

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Adds Scenario 182, which states the observable behaviour of the registry clause: dispatch and resume to the registry's address, the path override, refusal before any ledger write for a missing entry, an unreadable or malformed registry, or an entry declaring both forms, with no fallback; per-entry validation; the reconcile survey's unobservable report that leaves other factories observed; remote classification for telemetry; the recorded-pin fallback under the selection order; and a default switch that renames nothing. The revise that accepts it MUST add a tests/heading-coverage.json entry for the new heading.

### Motivation

Load-bearing behaviour MUST carry a Gherkin scenario beside its clause, and the factory dispatch that implements the clause references this scenario in its Definition of Done.

### Proposed Changes

Insert the following scenario into `scenarios.md` in numeric position, immediately before `## Scenario 183` (182 is unused on master):

````markdown
## Scenario 182 — A registry-backed factory resolves its address from the host registry, and an unresolvable one refuses before claim

```gherkin
Feature: Factory addresses come from a host registry, not from committed configuration
  As the maintainer of a fleet whose factories move between machines
  I want a committed factory entry to name no machine
  So that moving a factory is a provisioning change, never a repository change

  Background:
    Given dispatcher.factories declares a factory named "petri" with "registry": true and no server
    And LIVESPEC_FABRO_FACTORY is unset

  Scenario: A registry-backed factory dispatches to the address the registry names
    Given the factory registry maps "petri" to a server address
    When an item is dispatched to "petri"
    Then the Fabro run is created on the server address the registry maps "petri" to
    And the item's dispatch-factory record names "petri" and that server address

  Scenario: Resume resolves the same address
    Given the factory registry maps "petri" to a server address
    And an item whose dispatch to "petri" left a resumable run
    When the item is resumed
    Then the resume addresses the server address the registry maps "petri" to

  Scenario Outline: The registry path is the override when it is set and non-empty, and the default path otherwise
    Given LIVESPEC_FABRO_FACTORY_REGISTRY is <override>
    And the file at <read path> maps "petri" to a server address
    And the file at <other path> holds no entry for "petri"
    When an item is dispatched to "petri"
    Then the Fabro run is created on the server address the file at <read path> maps "petri" to

    Examples:
      | override                 | read path                          | other path                         |
      | set to a test file       | that test file                     | /etc/livespec/fabro-factories.json |
      | unset                    | /etc/livespec/fabro-factories.json | a test file                        |
      | set to the empty string  | /etc/livespec/fabro-factories.json | a test file                        |

  Scenario Outline: An unresolvable registry refuses before any ledger write and never falls back
    Given the factory registry <registry state>
    When an item is dispatched to "petri"
    Then the dispatch is refused naming "petri" and the registry path
    And the item's status, metadata and comments are unchanged
    And no Fabro run is created on any server

    Examples:
      | registry state                                         |
      | file is absent                                         |
      | file exists but cannot be read                         |
      | file does not parse as JSON                            |
      | file's top-level value is a list                       |
      | file has no entry named "petri"                        |
      | file maps "petri" to a string rather than an object    |
      | file maps "petri" to an object with no server          |
      | file maps "petri" to an object whose server is a number |
      | file maps "petri" to an object whose server is "   "   |
      | file maps "petri" to an object with a valid server and a docker_host of "   " |
      | file maps "petri" to an object with a valid server and a docker_host that is a number |

  Scenario: Only the selected entry is validated
    Given the factory registry maps "petri" to a server address and maps "legacy" to null
    When an item is dispatched to "petri"
    Then the Fabro run is created on the server address the registry maps "petri" to

  Scenario Outline: An entry declaring the registry together with a committed address refuses before any ledger write
    Given dispatcher.factories instead declares "petri" with "registry": true and a <committed key> value
    And the factory registry maps "petri" to a server address
    When an item is dispatched to "petri"
    Then the dispatch is refused naming "petri"
    And the item's status, metadata and comments are unchanged
    And no Fabro run is created on any server

    Examples:
      | committed key |
      | server        |
      | docker_host   |

  Scenario: The registry entry's docker_host is the factory's container-daemon address
    Given the factory registry maps "petri" to an object carrying a server address and a docker_host value
    When the reconcile pass sweeps the sandbox containers of every declared factory
    Then it reads "petri"'s containers through that docker_host value

  Scenario: A registry entry with no docker_host declares no container-daemon address
    Given the factory registry maps "petri" to an object carrying only a server address
    When the reconcile pass sweeps the sandbox containers of every declared factory
    Then the sweep reports "petri"'s sandbox containers as unobserved, naming "petri"
    And it opens no container-daemon connection for "petri"

  Scenario: The reconcile survey reports an unresolvable registry-backed factory as unobservable and still observes the others
    Given dispatcher.factories also declares a factory "legacy" with a server value whose Fabro server answers and holds one run
    And the factory registry has no entry named "petri"
    When the Dispatcher surveys every declared factory's runs
    Then the survey reports "petri" as unobservable, naming it
    And it does not report "petri" as holding no runs
    And it reports the one run "legacy" holds

  Scenario: A journal liveness read of an unresolvable registry-backed factory is unobservable
    Given the factory registry has no entry named "petri"
    And a dispatch journal row names "petri" as the factory of a run
    When the Dispatcher asks whether that run is live
    Then the answer is unobservable, naming "petri"
    And the run is not treated as gone

  Scenario: An availability-evidence read of an unresolvable registry-backed factory is unobservable
    Given the factory registry has no entry named "petri"
    When the ACP fallback availability evidence for "petri" is read
    Then that evidence is reported unobservable, naming "petri"
    And it is not read as an available or exhausted provider

  Scenario: The needs-human valve survives an unresolvable registry-backed factory
    Given the factory registry has no entry named "petri"
    And an item rests at a needs-human valve whose run was dispatched to "petri"
    When the needs-human valve list is assembled
    Then the item is listed at its valve
    And only that item's run enrichment is missing

  Scenario: A registry-backed factory is classified as remote for run-turn telemetry
    Given the factory registry maps "petri" to a server address
    And "petri" declares no run-turn telemetry export
    When the run-turn telemetry observability of "petri" is assessed
    Then "petri" is classified as a remote factory, exactly as an entry carrying a server value is

  Scenario: A recorded pin to an undeclared name still falls back to the default
    Given the factory registry maps "petri" to a server address
    And an item whose recorded dispatch factory is "hp"
    And dispatcher.factories no longer declares "hp"
    And dispatcher.default_factory names "petri"
    When the item is dispatched with no --factory flag
    Then it is dispatched to "petri"

  Scenario: Switching the default instance renames nothing
    Given dispatcher.factories also declares a registry-backed factory "next"
    And the factory registry maps both "petri" and "next" to server addresses
    And an unpinned item and an item whose recorded dispatch factory is "petri"
    When dispatcher.default_factory is changed from "petri" to "next"
    And both items are dispatched with no --factory flag
    Then the unpinned item is dispatched to "next"
    And the item recorded to "petri" is dispatched to "petri"
```
````
