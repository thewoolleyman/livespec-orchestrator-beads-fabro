---
topic: factory-addresses-from-a-gitops-registry
author: claude-opus-5-5
created_at: 2026-10-15T06:36:00Z
---

## Proposal: Factory addresses resolved from a host registry

### Target specification files

- SPECIFICATION/contracts.md

### Summary

A dispatcher.factories entry MAY declare "registry": true instead of a server value; its server address is then resolved by factory name from a host-side registry file that the fleet's provisioning renders from its inventory. Unresolvable registry-backed factories MUST be refused before claim and MUST NOT fall back to the ambient local target. The recorded-pin fallback is unchanged, and factory names SHOULD name instances while dispatcher.default_factory alone carries which instance serves.

### Motivation

The maintainer ruled on 2026-10-15 (plan bd-ib-fyozyd, petri-factory-on-gmktec) that no committed factory entry may name a machine hostname, so that a factory is bound to a machine only in the gitops inventory, and the factory can move to gmktec-xubuntu now and onto Kubernetes later without repository changes. Measured: fifteen fleet repositories commit factory tables whose server values name hp-xubuntu or vps. A Tailscale Service cannot provide a machine-free name (only tagged devices host one, agents may not add tags, and tagging gmktec would remove it from the member SSH grant), and HTTPS through tailscale serve rules out DNS aliases. Today an entry with no server resolves to the ambient local Fabro target, so simply deleting server values would silently re-route dispatches; the refusal rule exists to close that. The naming rule and the recorded-pin note were agreed with the fabro-currency plan, which owns the cutover: 425 items in this tenant record the factory name hp, and a renamed factory re-routes their later dispatches to the default rather than refusing them.

### Proposed Changes

Insert the following subsection into `contracts.md` §"Dispatcher policy settings", immediately after the subsection "### Sandbox image source" and before the next `## ` heading:

```markdown
### Factory addresses resolved from a host registry

A `dispatcher.factories` entry MAY declare `"registry": true` in place of a
`server` value. The server address of such a REGISTRY-BACKED entry MUST be
resolved by the entry's own name from the factory registry: a JSON file whose
path is the value of `LIVESPEC_FABRO_FACTORY_REGISTRY` when that variable is set
and non-empty, and otherwise `/etc/livespec/fabro-factories.json`. The registry's
top-level value MUST be an object mapping factory names to objects, each carrying
a non-empty `server` string. The registry is host state rendered by the fleet's
provisioning from its inventory; no committed file in a governed repository
writes it. An entry that carries `server` keeps its existing meaning unchanged.

The Dispatcher MUST refuse, before any claim, ledger mutation or Fabro run
creation, a dispatch whose resolved factory is registry-backed when the registry
file is absent or unreadable, is not a JSON object, has no entry for that factory
name, or gives that entry no non-empty `server` string. The refusal MUST name the
factory and the registry path it read. The Dispatcher MUST NOT fall back to the
ambient local Fabro target, to `dispatcher.default_factory`, or to any other
factory in that case. An entry declaring both `"registry": true` and `server`
MUST be refused the same way, naming the factory.

Every Dispatcher surface that turns a declared factory into an address MUST use
this one resolution: dispatch and resume, the reconcile survey of declared
factories, the liveness question asked of each factory a journal names, and the
availability-evidence reads of §"Factory-configurable ACP fallback priority". A
survey or read that cannot resolve a registry-backed factory MUST report that
factory as unobservable, naming it, and MUST NOT skip it silently or treat it as
holding no runs. A resolved registry-backed dispatch MUST record the resolved
server address in the item's dispatch-factory record exactly as a `server` entry
does.

The registry refusal applies only to resolving a DECLARED entry. A recorded
factory name that `dispatcher.factories` no longer declares keeps its existing
treatment: it is ignored and the dispatch falls back to
`dispatcher.default_factory`. Renaming a factory therefore re-routes the later
dispatches of every item that recorded the old name onto the default factory.

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

Adds Scenario 182, which states the observable behaviour of the registry clause: dispatch to the registry's address, refusal before claim for a missing entry or an unreadable registry with no local fallback, an unobservable report from the reconcile survey, and an unchanged recorded-pin fallback. The revise that accepts it MUST add a tests/heading-coverage.json entry for the new heading.

### Motivation

Load-bearing behaviour MUST carry a Gherkin scenario beside its clause, and the factory dispatch that implements the clause references this scenario in its Definition of Done.

### Proposed Changes

Append the following scenario to `scenarios.md` after the highest-numbered scenario (number 182; 180 is reserved by a pending proposal and 181 is in use):

````markdown
## Scenario 182 — A registry-backed factory resolves its address from the host registry, and an unresolvable one refuses before claim

```gherkin
Feature: Factory addresses come from a host registry, not from committed configuration
  As the maintainer of a fleet whose factories move between machines
  I want a committed factory entry to name no machine
  So that moving a factory is a provisioning change, never a repository change

  Scenario: A registry-backed factory dispatches to the address the registry names
    Given dispatcher.factories declares a factory named "petri" with "registry": true and no server
    And the factory registry maps "petri" to a server address
    When an item is dispatched to "petri"
    Then the Fabro run is created on the server address the registry maps "petri" to
    And the item's dispatch-factory record names "petri" and that server address

  Scenario: A registry with no entry for the factory refuses before claim
    Given dispatcher.factories declares a factory named "petri" with "registry": true
    And the factory registry has no entry named "petri"
    When an item is dispatched to "petri"
    Then the dispatch is refused naming "petri" and the registry path
    And the item's status is unchanged and no Fabro run exists for it

  Scenario: An unreadable registry refuses rather than falling back to a local server
    Given dispatcher.factories declares a factory named "petri" with "registry": true
    And the factory registry file is absent
    When an item is dispatched to "petri"
    Then the dispatch is refused naming "petri" and the registry path
    And no Fabro run is created on any server

  Scenario: The reconcile survey reports an unresolvable registry-backed factory as unobservable
    Given dispatcher.factories declares a registry-backed factory the registry does not name
    When the Dispatcher surveys every declared factory's runs
    Then the survey reports that factory as unobservable, naming it
    And it does not report that factory as holding no runs

  Scenario: A recorded pin to an undeclared name still falls back to the default
    Given an item whose recorded dispatch factory is "hp"
    And dispatcher.factories no longer declares "hp"
    And dispatcher.default_factory names a registry-backed factory the registry maps
    When the item is dispatched without an explicit factory
    Then it is dispatched to the default factory
```
````
