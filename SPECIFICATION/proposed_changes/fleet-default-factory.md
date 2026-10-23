---
topic: fleet-default-factory
author: claude-opus-5-5:fabro-currency
created_at: 2026-10-23T01:08:11Z
---

## Proposal: The factory registry carries the fleet default factory and each factory's client settings

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Let the host factory registry designate a fleet default factory and hold each factory's client settings (bin, secret_channel, environment), so a repository that names the fleet default dispatches wherever the registry designates, and moving the fleet default is a provisioning change with no repository commit.

### Motivation

On 2026-10-22 the maintainer asked (coordinator ruling R679): 'Why aren't we making a fleet-wide configuration that just says what factory to dispatch to and then roll that out everywhere? Are we duplicating?' We are. Fifteen fleet repositories each commit dispatcher.default_factory plus a per-factory client block (bin, secret_channel, environment), and twelve specifications ratify the literal default name. So the R668 cutover from legacy to petri took one config PR per repository, plus a spec revision in every repository whose specification pinned the old name (livespec v228, livespec-overseer v066, livespec-console-beads-fabro v056, and more on the petri seat). §"Factory addresses resolved from a host registry" already moved factory ADDRESSES into the registry for exactly this reason. This proposal moves the remaining per-repository duplication, which factory a repository uses by default and how to speak to it, into the same registry. Work-item bd-ib-ep4eeo.

### Proposed Changes

Amend SPECIFICATION/contracts.md §"Factory addresses resolved from a host registry" as follows.

1. After the paragraph that defines the registry's per-factory `server` and `docker_host` values, add:

"The factory registry MAY designate a FLEET DEFAULT: a top-level `default` key whose value is a string naming one of the registry's factory entries. The key is reserved, so no factory may be named `default`. A repository whose committed `dispatcher.default_factory` is the reserved value `fleet` MUST resolve its default factory to the registry's fleet default. A `dispatcher.default_factory` that names a factory keeps its existing meaning and overrides the fleet default for that repository. An ABSENT `dispatcher.default_factory` keeps its existing treatment, so an adopter repository outside the fleet, which has no registry, is unaffected. A factory reached through the fleet default that the repository's `dispatcher.factories` does not declare MUST be treated as a registry-backed entry of that name, so moving the fleet default to a factory no repository has declared needs no repository commit."

2. Add:

"A registry factory entry MAY carry `bin`, `secret_channel` and `environment`, each with exactly the meaning that key has on a committed `dispatcher.factories` entry. For a registry-backed factory, each of the three MUST be taken from the committed entry when the committed entry declares it, and otherwise from the registry entry; a key declared in neither keeps its existing absent-key treatment. Every validation and refusal a committed value of those keys receives MUST apply equally to a registry-supplied value, naming the registry path as its source. A factory's dev token stays keyed by the factory name, unchanged."

3. Extend the pre-claim refusal paragraph: the Dispatcher MUST refuse, before any claim, ledger write or Fabro run creation, a dispatch that resolves its default through `fleet` when the registry file is absent or unreadable, has no `default` key, or has a `default` value that is not a string naming a registry factory entry. The refusal MUST name the registry path and what it lacked, and the Dispatcher MUST NOT fall back to the ambient local target, to any committed factory, or to any other registry entry.

4. In the selection order ("... and otherwise `dispatcher.default_factory`") and throughout §"Factory overflow selection", the factory a repository uses by default MUST be read as the RESOLVED default factory: the named `dispatcher.default_factory`, or the registry's fleet default when it is `fleet`. In particular `dispatcher.overflow_factories` MUST NOT name the resolved default factory.

5. Replace the closing paragraph ("Which instance serves a repository by default MUST be carried only by `dispatcher.default_factory` ...") with:

"A factory name SHOULD name the Fabro server instance it addresses and SHOULD stay the same for that instance's whole life. A fleet member repository SHOULD set `dispatcher.default_factory` to `fleet` and SHOULD NOT commit `bin`, `secret_channel` or `environment` for a registry-backed factory, so that moving the fleet's default from one instance to another, or changing how that instance is spoken to, is a change to the provisioning inventory alone. A repository that names a factory in `dispatcher.default_factory` opts out of that move by design."

Add to SPECIFICATION/scenarios.md a new scenario, "## Scenario 241 — A repository naming the fleet default dispatches to the factory the registry designates, and moving the fleet default re-routes it with no repository commit", with a gherkin block covering four cases:
- Given dispatcher.default_factory is "fleet" and the registry's default names "petri", which the registry maps to a server and gives bin, secret_channel and environment. When an item is dispatched, then the Fabro run is created on petri's registry server using petri's registry client settings, and the dispatch-factory record names "petri".
- Given the same repository, when only the registry's default is changed to another registry factory, then the next unpinned dispatch is created on that factory, and the repository's committed configuration is unchanged.
- Given dispatcher.default_factory names "legacy", which the repository declares, then the dispatch goes to legacy whatever the registry's default names.
- Given dispatcher.default_factory is "fleet" and the registry has no default key, then the dispatch is refused before any claim, naming the registry path, and no item is claimed.

The scenario MUST be linked in tests/heading-coverage.json to the clauses above in the same revision.

**Amendments after independent review (gpt-6-astra round 1, BLOCKERS 2):**

6. Recorded pins survive a moved fleet default. Amend the recorded-factory rule ("A recorded factory name that `dispatcher.factories` no longer declares keeps its existing treatment ...") so that a recorded factory name the dispatch reached through `fleet` MUST continue to resolve, by that recorded name, as a registry-backed entry even when the repository does not declare it, and even after the registry's fleet default moves to another factory. A resume or re-dispatch carrying such a pin MUST go to the recorded factory, and MUST be refused before any claim, naming the factory and the registry path, when the registry no longer resolves that name. It MUST NOT be silently re-routed to the current fleet default. The existing treatment of an undeclared recorded name is unchanged for a name that was NOT reached through `fleet`.

7. A factory selected through `fleet` always takes its address from the registry. Every factory selected through `fleet` MUST resolve its server and container-daemon address through the registry, including a factory the repository also declares. A committed `dispatcher.factories` entry for that name that carries `server` or `docker_host` MUST be refused before any ledger write, naming the factory, because two addresses for one selected factory is a conflict, not a precedence question.

Add to Scenario 241 two cases:
- Given dispatcher.default_factory is "fleet", an item whose dispatch was recorded on "petri" through the fleet default, and the registry's default since moved to another factory. When the item is resumed, then the resume goes to "petri", resolved through the registry.
- Given dispatcher.default_factory is "fleet", the registry's default names "petri", and the repository's committed "petri" entry carries a server address. When an item is dispatched, then the dispatch is refused before any claim, naming "petri", and no item is claimed.

**Amendment after independent review (gpt-6-astra round 2, BLOCKERS 1):**

8. A fleet-derived pin keeps its place in the selection order. Amendment 6 governs only the RECORDED-FACTORY step of the selection order. An explicit `--factory`, or a set and non-empty `LIVESPEC_FABRO_FACTORY`, still takes precedence over a fleet-derived recorded pin exactly as it does over any recorded factory. In §"Factory overflow selection", the eligibility sentence ("Overflow selection applies ONLY to a dispatch ... that has ... no recorded factory that `dispatcher.factories` still declares") MUST also exclude a dispatch carrying a preserved fleet-derived recorded pin, whether or not the repository declares that name. Such a dispatch is pinned, takes no overflow ranking, and goes to its recorded factory.

Add to Scenario 241 two cases:
- Given dispatcher.default_factory is "fleet", dispatcher.overflow_factories is non-empty, and an item with a fleet-derived recorded pin on an undeclared "petri". When the item is resumed after the fleet default moved, then the resume goes to "petri" and no overflow ranking is journaled.
- Given the same item, when it is dispatched with an explicit --factory naming another declared factory, then the dispatch goes to that explicit factory.

**Amendment accommodating v203 (fresh-dispatch-ignores-recorded-factory, bd-ib-2b2uqa):**

9. Amendments 6 and 8 apply to a RESUME only. Revision v203 restricted the recorded-factory step of the selection order to a dispatch whose route is `resume` (an invocation of `resume --item`, or a `dispatch` or `loop` pass whose recovery routing routes the item `resume`), and made every other dispatch a FRESH dispatch that reads no recorded factory. This proposal amends the v203 text of §"Factory addresses resolved from a host registry" and §"Factory overflow selection", not the v202 text quoted in amendments 6 and 8. Accordingly:
   - In amendment 6, "A resume or re-dispatch carrying such a pin" reads "A resume carrying such a pin", and the preserved resolution of a fleet-derived recorded name, together with its refusal when the registry no longer resolves that name, applies only to a resume.
   - In amendment 8, the overflow exclusion of a dispatch carrying a preserved fleet-derived recorded pin applies only to a resume. A fresh dispatch of an item whose recorded factory was reached through `fleet` MUST resolve the CURRENT resolved default factory, or factory overflow selection when it is configured, exactly as any fresh dispatch does under v203, and its fleet-derived record pins nothing.
   - Explicit `--factory` and a set and non-empty `LIVESPEC_FABRO_FACTORY` keep their precedence over both.

In Scenario 241, the second case reads "then the next fresh dispatch of any item, including an item whose dispatch was recorded on the old default, is created on that factory, and the repository's committed configuration is unchanged". Add one case:
- Given dispatcher.default_factory is "fleet", an item whose dispatch was recorded on "petri" through the fleet default, and the registry's default since moved to "next". When the item is dispatched with dispatch --item and recovery routing routes it fresh, then the run is created on "next", and the admission claim stamp and the dispatch-factory record name "next".

**Amendments after independent review (gpt-6-astra round 4, BLOCKERS 2):**

10. Scope of the registry refusals. In §"Factory addresses resolved from a host registry", replace:

"The registry refusal applies only to resolving a DECLARED, registry-backed entry, and the undeclared-name refusal only to an EXPLICIT selection."

with:

"The registry refusal applies to resolving a DECLARED, registry-backed entry, a factory reached through the reserved default value `fleet`, and a preserved fleet-derived recorded factory selected by a resume; the fleet-default refusal of change 3 applies to every dispatch that resolves its default through `fleet`. The undeclared-name refusal applies only to an EXPLICIT selection: an explicit `--factory` or a set and non-empty `LIVESPEC_FABRO_FACTORY` MUST still name an entry of a declared `dispatcher.factories`, and a registry entry the repository does not declare is NOT selectable explicitly. A fresh dispatch MUST NOT validate, resolve or refuse on the item's recorded factory, fleet-derived or not."

In the same section, replace "A `dispatcher.default_factory` that names no declared entry keeps its existing treatment as well; this clause does not govern it." with "A `dispatcher.default_factory`, other than the reserved value `fleet`, that names no declared entry keeps its existing treatment as well; this clause does not govern it."

11. Scenario 241's gherkin. The new scenario "## Scenario 241 — A repository naming the fleet default dispatches to the factory the registry designates, and moving the fleet default re-routes it with no repository commit" MUST carry exactly the cases below. This list SUPERSEDES every Scenario 241 case list given earlier in this proposal (after change 5 and in amendments 7, 8 and 9). In every case, `dispatcher.factories` is declared and does NOT declare "petri" or "next" unless the case says so, and "legacy" is a declared factory with a committed `server`.

```gherkin
Feature: The factory registry designates the fleet default factory and carries its client settings
  As a maintainer moving the whole fleet from one Fabro instance to another
  I want each repository to name the fleet default rather than a factory
  So that moving the default is a change to the provisioning inventory alone

Background:
  Given the factory registry maps "petri" and "next" to server addresses
  And the registry gives "petri" a bin, a secret_channel and an environment

Scenario: An undeclared registry default receives a fresh dispatch
  Given dispatcher.default_factory is "fleet" and the registry's default is "petri"
  When an item is dispatched with no explicit factory and its route is fresh
  Then the admission claim stamp names "petri"
  And the Fabro run is created on petri's registry server with petri's registry bin, secret_channel and environment
  And the item's dispatch-factory record names "petri"

Scenario: Moving the fleet default re-routes the next fresh dispatch with no repository commit
  Given dispatcher.default_factory is "fleet" and the registry's default is "petri"
  And an item whose dispatch was recorded on "petri" through the fleet default
  When only the registry's default is changed to "next"
  And the item is dispatched with no explicit factory and its route is fresh
  Then the run is created on "next" and the claim stamp and dispatch-factory record name "next"
  And the repository's committed configuration is unchanged

Scenario: A named default overrides the fleet default
  Given dispatcher.default_factory is "legacy"
  When an item is dispatched with no explicit factory and its route is fresh
  Then the run is created on "legacy" whatever the registry's default names

Scenario: An absent default keeps its existing treatment outside the fleet
  Given dispatcher.default_factory is absent and no factory registry exists on the host
  When an item is dispatched with no explicit factory
  Then the dispatch resolves its target exactly as it did before this revision

Scenario Outline: A committed client setting outranks the registry's, key by key
  Given dispatcher.default_factory is "fleet" and the registry's default is "petri"
  And the committed "petri" entry declares only <key>
  When an item is dispatched with no explicit factory and its route is fresh
  Then the run uses the committed <key> and the registry's value for each other client key
  Examples:
    | key            |
    | bin            |
    | secret_channel |
    | environment    |

Scenario: A client key neither source declares keeps its absent-key treatment
  Given dispatcher.default_factory is "fleet" and the registry's default is "next"
  And neither the registry nor the repository gives "next" an environment
  When an item is dispatched with no explicit factory and its route is fresh
  Then the run is created with the absent-environment treatment a committed entry without that key receives

Scenario: An invalid registry-supplied client setting is refused naming the registry
  Given dispatcher.default_factory is "fleet" and the registry's default is "petri"
  And the registry gives "petri" a secret_channel value a committed entry would be refused for
  When an item is dispatched
  Then the dispatch is refused before any claim, ledger write or Fabro run
  And the refusal names the registry path as the source of the value

Scenario Outline: A fleet default the registry cannot supply is refused before any claim
  Given dispatcher.default_factory is "fleet"
  And <registry state>
  When an item is dispatched
  Then the dispatch is refused before any claim, ledger write or Fabro run, naming the registry path and what it lacked
  And the Dispatcher falls back to no committed factory, no other registry entry and no ambient local target
  Examples:
    | registry state                                                  |
    | the registry file is absent                                     |
    | the registry file is unreadable                                 |
    | the registry has no default key                                 |
    | the registry's default is not a string                          |
    | the registry's default names no registry factory entry          |

Scenario: The reserved key cannot name a factory
  Given the factory registry carries a factory entry named "default"
  When an item is dispatched through the fleet default
  Then the registry is refused as invalid, naming the reserved key

Scenario Outline: A committed address for a fleet-selected factory is a conflict
  Given dispatcher.default_factory is "fleet" and the registry's default is "petri"
  And the committed "petri" entry carries <address key>
  When an item is dispatched
  Then the dispatch is refused before any ledger write, naming "petri"
  Examples:
    | address key |
    | server      |
    | docker_host |

Scenario: A resume keeps a fleet-derived pin after the fleet default moves
  Given dispatcher.default_factory is "fleet"
  And an item whose dispatch was recorded on "petri" through the fleet default
  And the registry's default has since moved to "next"
  When the item's route is resume, through resume --item or recovery routing's resume route
  Then the resume is submitted to "petri", resolved through the registry
  And no overflow-selection journal record is written, even when dispatcher.overflow_factories is non-empty

Scenario: A resume whose fleet-derived pin the registry no longer resolves is refused
  Given the same item and the registry no longer has a "petri" entry
  When the item's route is resume
  Then the resume is refused before any claim, naming "petri" and the registry path
  And it is not re-routed to the current fleet default

Scenario: A fresh dispatch ignores an unresolvable fleet-derived pin
  Given the same item and the registry no longer has a "petri" entry
  When the item is dispatched with no explicit factory and its route is fresh
  Then the run is created on the registry's current default "next"
  And nothing is refused on account of the recorded "petri"

Scenario Outline: An explicit selection outranks a fleet-derived pin on a resume
  Given dispatcher.default_factory is "fleet" and "legacy" is declared
  And an item whose dispatch was recorded on "petri" through the fleet default, whose route is resume
  When the resume is made with <explicit selection> naming "legacy"
  Then the resume is submitted to "legacy"
  Examples:
    | explicit selection           |
    | --factory                    |
    | a set LIVESPEC_FABRO_FACTORY |

Scenario: A fresh fleet dispatch takes overflow selection and records its winner
  Given dispatcher.default_factory is "fleet", the registry's default is "petri", and dispatcher.overflow_factories is ["legacy"]
  And "petri" reports no free slot and "legacy" has a free slot
  And an item whose dispatch was recorded on "petri" through the fleet default
  When the item is dispatched with no explicit factory and its route is fresh
  Then one overflow-selection journal record lists "petri" and "legacy" and names chosen "legacy"
  And the admission claim stamp, the submitted run and the dispatch-factory record all name "legacy"

Scenario: Overflow may not name the resolved default factory
  Given dispatcher.default_factory is "fleet", the registry's default is "petri", and dispatcher.overflow_factories is ["petri"]
  When an item is dispatched
  Then the configuration is refused before any item is claimed, naming "petri"
```

The revision MUST add a tests/heading-coverage.json row for this heading in the same change.

**Amendments after independent review (gpt-6-astra round 5, BLOCKERS 2):**

12. Recorded fleet-derived targets are attributable and observable. A factory name a dispatch reached through `fleet` is a RECORDED-TARGET factory: it is not declared by this proposal, and amendment 10's rule that only a declared entry is explicitly selectable is unchanged. For OBSERVATION and RECOVERY of a recorded run, and for no other purpose, every rule that addresses a recorded factory by "its declared server target" or treats a stamp that "names no declared factory" as unattributable MUST also accept a recorded-target factory, resolving its address through the registry under its recorded name, including after the fleet default has moved. Accordingly:
   - In §"Stranded claim release", the *Run state* measurement ("that factory's answer for that run, asked by the factory's declared server target") reads "asked by the factory's declared server target, or, for a recorded-target factory, by the server the registry resolves for its recorded name".
   - Hold reason 1 ("`claim-unattributable`: the item carries no readable run stamp, or the stamp names no declared factory.") reads "`claim-unattributable`: the item carries no readable run stamp, or the stamp names a factory that is neither declared nor a recorded-target factory." A stamp naming a recorded-target factory whose name the registry no longer resolves is held `factory-unobservable`, naming the factory and the registry path, and is never treated as unattributable or as holding no run.
   - Every other surface listed in the paragraph beginning "Every surface that turns a declared factory into an address MUST use this one resolution" (the reconcile survey, a liveness read, the needs-human valve enrichment, the run-event projection, and the others it names) reads a recorded-target factory the same way, and reports one the registry cannot resolve as unobservable, naming it.
   - In amendment 10, "A fresh dispatch MUST NOT validate, resolve or refuse on the item's recorded factory" reads "For factory SELECTION, a fresh dispatch MUST NOT validate, resolve or refuse on the item's recorded factory; the readers v203 preserves, and recovery routing's measurements of an earlier run, still read it."

13. Amendment 11's case "An invalid registry-supplied client setting is refused naming the registry" is replaced by:

```gherkin
Scenario: An invalid registry-supplied client setting is refused as a committed one would be, naming the registry
  Given dispatcher.default_factory is "fleet" and the registry's default is "petri"
  And the committed "petri" entry declares no secret_channel
  And the registry gives "petri" a secret_channel value a committed entry would be refused for
  When an item is dispatched
  Then the dispatch receives the same refusal, at the same point and with the same effects, as a committed secret_channel of that value receives
  And the refusal names the registry path as the source of the value
```

Amendment 11's Scenario Outline "A committed client setting outranks the registry's, key by key" gains a second axis, so it also runs with `dispatcher.default_factory` naming a declared registry-backed factory (`"registry": true`) in place of `fleet`. Amendment 11's case "Overflow may not name the resolved default factory" declares "petri" as a registry-backed factory in `dispatcher.factories`, so that the case isolates the resolved-default prohibition.

Add to Scenario 241:

```gherkin
Scenario: A stranded claim on a fleet-derived factory is recovered after the fleet default moves
  Given dispatcher.default_factory is "fleet"
  And an item active and assigned fabro whose run stamp names "petri", reached through the fleet default, and this host
  And the registry's default has since moved to "next" while its "petri" entry remains
  And the run on "petri" has terminated and no live process owns the item
  When the reconcile pass surveys the claim
  Then the run state is read from the server the registry resolves for "petri"
  And the claim is not held as claim-unattributable

Scenario: A stranded claim on a fleet-derived factory the registry no longer resolves is held unobservable
  Given the same claim and the registry no longer has a "petri" entry
  When the reconcile pass surveys the claim
  Then the claim is held as factory-unobservable, naming "petri" and the registry path
  And it is not treated as holding no run
```
