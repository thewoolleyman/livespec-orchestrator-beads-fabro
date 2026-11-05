## The maintainer's statement of what done means

Include deep research into fabro/petri best practices and other ai dark factories, with astra and fable subagents, to determine best practices and ideas for direction.  Acdd this to existing draft - then proceed with draft, etc., and start plan for me to discuss

## Definition of Done assertions derived from that statement

- Every way a factory run ends (needs-human, the Dispatcher's run-wall-budget, stall-watchdog and restart cancels, a cancel made outside the Dispatcher, a publish_draft failure, and a fabro rm -f) leaves the run's latest committed tree on a named ref on origin, with its commit id recorded on the item's ledger.
- A re-dispatch of an item whose earlier run ended without merging starts from that run's preserved tree instead of redoing the stages that run had finished.
- Adding a run-ending or run-removal path that skips preservation is caught by a check before it merges, rather than found later as a lost tree.
- Preserved run refs on origin are removed by a stated retention rule once they are no longer needed, so they do not accumulate.
- Over the seven days after the fixes are released, no factory run ending recorded in any fleet dispatch journal loses committed work.
- The plan's research directory holds a best-practices note on run-work preservation, drawn from Fabro and Petri and from other AI software factories by independent Astra and Fable research sessions, and the maintainer's chosen direction is recorded against it.

## Charter — 2026-11-04 (why this plan exists)

### The maintainer's words, verbatim

The direction that opened the plan, relayed by legacy-coordinator-agent (about 2026-11-04 20:0xZ):

> spin a dedicated plan and open it in new herdr tab for the architectural decision discussed above, and flag it as a maintainer item for me to drive and decide direction.

The maintainer's answer, in this tab, to "What does DONE mean for this plan, in your words?" (asked with a five-point draft, reproduced as assertions 1 to 5 above):

> Include deep research into fabro/petri best practices and other ai dark factories, with astra and fable subagents, to determine best practices and ideas for direction.  Acdd this to existing draft - then proceed with draft, etc., and start plan for me to discuss

So assertions 1 to 5 are the draft the maintainer adopted, and assertion 6 is the research the maintainer added.
"astra" is the Codex model `gpt-6-astra`, and "fable" is Claude Fable 5.1.

### This plan is maintainer-driven

The maintainer chooses the direction. Until a ruling is recorded as a scope event on the epic, this plan:

- files no implementation children;
- dispatches nothing;
- does not cancel the per-path fixes that are already moving (bd-ib-adcaa6, bd-ib-vraou4, bd-ib-ds4yrm).

The direction the maintainer picks should absorb those three items, not throw them away.

### The problem

A factory run's work survives only on some endings. Today only the needs-human ending pushes the run's committed tree to a ref, `refs/heads/needs-human/<id>`, from the workflow's `needs_human` command node. Every other ending has lost the tree, or can lose it, unless someone writes a separate patch for that path:

- **The Dispatcher's own run-wall-budget cancel (Scenario 175).**
  - Run 01M6KBH30NJA of bd-ib-yuwftp hit the 21600 s budget at 19:28Z on 2026-11-04.
  - Its preserve-by-reference pointer, 01a1a804-ca17-7126-8ef0-795f5779972d, held only a 78-byte `fix@2` diff.patch.
  - `fabro rm -f` then removed the run, losing about six hours of P1 critical-path work: two review rounds, review_fix, and three fix laps.
  - Fix item: bd-ib-ds4yrm.
- **The cancel-for-restart path** (bd-ib-adcaa6), and **a cancel made outside the Dispatcher** (bd-ib-vraou4).
- **Stall-watchdog cancels** (plan stall-watchdog-false-kills, bd-ib-laf735).
- **publish_draft's rebase onto a moved master** (bd-ib-tzj9x, plan publish-draft-green-work-loss, bd-ib-acrr56).
- **Any `fabro rm -f`, or a removal on the server side.**

So far the pattern has been one preservation patch per cancel path. Any path nobody remembered stays a loss.

On the maintainer's order, legacy-coordinator-agent has filed the invariant item **bd-ib-xdhe5z**: "No factory run ending ever removes or abandons a run before its committed tree is on a ref on origin". It is P1, pending-approval and classed spec-change. It states the rule only. The mechanism is this plan's decision, and the item is a child of this plan's epic.

### Research notes

- `002-preservation-decision-options-2026-11-04.md` lays out the decision.
  It is measured from the code and the ledger, and the code facts carry file and line citations.
- The best-practices research the maintainer added (assertion 6) lands as its own note. It comes from independent Astra and Fable research sessions on Fabro, Petri and other AI software factories.
