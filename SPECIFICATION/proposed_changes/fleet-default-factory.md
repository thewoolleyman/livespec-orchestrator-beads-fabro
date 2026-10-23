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
