Independent review of the cross-repository spec-change-tier direction

Verdict: adopt with named changes. The two reported gaps are real, but option B's claimed cost and its proposed retrieval strategy are incorrect as written. The foreign-specification hold and release lifecycle is also incomplete.

Scope and method: I reviewed the orchestrator checkout at 333ddf098d98, dev-tooling at 8250da20196c, runtime at a86e522e0309, the orchestrator's vendored runtime, the relevant git-jsonl consumer, and locally available pinned release objects. I ran only read-only source inspection and in-memory probes, with Python bytecode writes disabled. I did not query the live ledger, call a model, contact the forge, or independently reproduce the filing counts and dollar measurement. The janitor-refresh item's ledger state and cost figures remain supplied evidence from xrepo_direction.md:13,22.

In references below, O means /data/projects/livespec-orchestrator-beads-fabro, D means /data/projects/livespec-dev-tooling, R means /data/projects/livespec-runtime, and J means /data/projects/livespec-orchestrator-git-jsonl. O/commands means O/.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands. Line numbers refer to the inspected working files, except where a pinned release is explicitly named.

1. The existing behavior conforms to an explicit exemption; changing it requires ratification.

O/commands/_spec_change_tier_gate.py:200-229 classifies first and returns without a spec-stated judgement for every non-feature. Its specification reader uses only repo/SPECIFICATION at :328-333. O/SPECIFICATION/contracts.md:1571 expressly says bug, chore and non_functional items are never spec-change tier; O/SPECIFICATION/scenarios.md:8532-8535 requires a bug to route as today. O/SPECIFICATION/constraints.md:11-17 already establishes inheritance from livespec, so local-only retrieval is narrower than the governing material.

These findings justify an amendment, not a claim that the non-feature exemption is an implementation defect. Preserve the feature/partial/unstated rule while adding an explicit exception for a requested outcome that conflicts with an applicable binding requirement.

2. Option B's “clauses already in its prompt” and “only extra output tokens” claims are false.

The shipped classification prompt contains title, description and stored type only: O/.claude-plugin/scripts/_vendor/livespec_runtime/spec_stated.py:100-119. Its classify function accepts no specification input and returns one bare class word at :356-378. The upstream public contract says the same at R/SPECIFICATION/contracts.md:954. Only the subsequent feature judgement receives the condensed tree, at O/commands/_spec_change_tier_gate.py:230-235.

B can avoid an additional logical classifier invocation, but it must add specification input tokens to every classification. If features still take the existing judge call, their specification input is paid twice. Reprice B using actual input size, feature/non-feature classifications, provider attempts and cache behavior. Alternatively specify a genuinely combined class/coverage/conflict judgement and update the shared contract accordingly. Neither alternative is merely a wider reply parser.

3. The proposed same-ceiling union fails a concrete retrieval probe.

I combined O's current five spec files with the specs from D v1.187.0 and livespec v0.45.1, excluding history and proposals, using repository-qualified file keys. These are the pins identified below. The combined corpus had 17 files and 3,165,777 characters. Using the janitor-refresh title as the statement, the current condenser selected 24 complete clauses from O alone and zero complete clauses from the combined corpus. The combined prompt omitted the Suite-green replay leg body.

A second probe with full repository names in the keys measured a 200,000-character outer ceiling, 136,718 characters after citation-correction headroom, and an initial rendered judgement prompt of 182,171 characters. Thus the heading skeleton alone defeats the reserved budget; this is more severe than modest crowding out.

The mechanism is visible in O/commands/_spec_tree_condensation.py:116,214-237: every heading and an omission marker survive, before any body budget is spent. Full bodies enter only when they fit (:273-302). Correction headroom subtracts another heading inventory at O/commands/_spec_stated_citation.py:110-129. Ranking is lexical, not a completeness proof: O/commands/_spec_tree_relevance.py:30-49.

Replace “same selection under the same ceiling” with a tested retrieval design that makes applicable bodies available, budgets heading overhead, and reports unexamined material honestly. Test the actual classifier template's total size. A local-clause budget and targeted foreign retrieval are possible designs; either needs a measured recall control for the target clause and local clauses.

4. Foreign holds currently have no complete proposal, ratification, pin-adoption or release path.

O/commands/_spec_change_tier_gate.py:193 and O/commands/_spec_change_tier_wall.py:143-147 read ratified topics only under the target's local SPECIFICATION. O/commands/_dispatcher_spec_commitments.py:111-124 returns unqualified proposal stems from that history. The contract releases only after a linked accept/modify decision plus a fresh stated judgement: O/SPECIFICATION/contracts.md:1571.

Naming a violated dev-tooling clause does not identify where its amendment is filed. Ratifying an upstream amendment does not change the old specification a consumer still pins. A local proposal cannot amend an upstream contract.

Require an owner-qualified proposal link, resolution of its revision decision in the owning repository, adoption of the release containing that amendment by the consumer, and a fresh conflict/coverage check against the adopted set. Specify how multiple conflicts and multiple required proposals are represented. Also define release after the requested change is edited into conformance, without requiring an unnecessary spec amendment. Extend relinking, human release, drain eligibility and in-run checks to the same identities.

5. Updating the shared classifier/parser alone would break the existing consumers and can fail open.

O/commands/_drift_run_judge.py:138-155 accepts an item_class reply only if it is exactly one current class word. A richer JSON reply would be rejected by this runner before the new shared parser can accept it. O/commands/_spec_change_tier_gate.py:211-229 also assumes the successful return value is an ItemClass.

The shared persisted shape has no conflict field: R/SPECIFICATION/contracts.md:946-955. J/SPECIFICATION/contracts.md:558-573 requires a spec-change record to have a non-null partial/unstated verdict; J's codec enforces that at J/.claude-plugin/scripts/livespec_orchestrator_git_jsonl/spec_change_tier.py:156-176. A classification naming a violation does not satisfy that wire contract by itself. J's filing contract also explicitly exempts non-features at J/SPECIFICATION/contracts.md:121-147.

Ratify and implement a coordinated shared result schema, runner validation, consumers, record codecs and compatibility policy. Define how legacy class-only and tier-none records are invalidated so upgrading the plugin actually applies the new rule. Release the runtime, update both consumers' pins/vendor trees, and validate old-record reads and new-record writes. The runtime versioning policy explicitly treats public API and parse-contract changes as release-significant: R/SPECIFICATION/non-functional-requirements.md:150-170.

6. An unreadable governing specification is not merely “never reported as stated.”

The proposed rule holds on a named conflict. If a governing tree is unavailable, a classifier cannot name its conflict, so suppressing its clauses can silently admit the change. O/SPECIFICATION/contracts.md:1571 currently allows an unavailable classification to route as before, with an in-run backstop described specifically as refusing an unstated feature. O/SPECIFICATION/scenarios.md:8592-8596 exercises that limited backstop.

Define unavailable, partially examined, no conflict found, and conflict found as distinct outcomes. Decide the dispatch policy for unavailable required governing material. If intake remains fail-open, the in-run backstop must obtain the same governing set and detect contradictions for every class before implementation. A receipt alone does not enforce the intended boundary. Preserve already recorded holds during read/model failures.

7. Repository-qualified clause identity, applicability and precedence are necessary.

The runtime currently cites and validates bare H2 strings: R/livespec_runtime/spec_stated.py:63-67,174-183,208-216. O's clause provenance omits paths in its serialization at O/commands/_dispatcher_dod_clause_record.py:31-34, while CondensedClause excludes path from equality at O/commands/_spec_tree_condensation.py:141-153. The inspected union contains real repeated headings, including Lifecycle, Boundary, Versioning, and Delegated commit-time replay test runs.

Prefixing mapping keys prevents contracts.md file overwrites but does not disambiguate these returned headings or record identities. Use repository, resolved commit, file and heading for conflict citations and release decisions, together with the exact applicable requirement and its body digest.

Also define which imported obligations bind this consumer. An upstream repository's own layout and development rules do not automatically all become consumer obligations; R/SPECIFICATION/non-functional-requirements.md:8-23 expressly distinguishes contributor rules from consumer API contracts and names an inheritance precedence. O/SPECIFICATION/contracts.md:3663 supplies a concrete scoped refinement to inherited hook selection. A flat bag of MUST sentences can falsely hold legitimate local exceptions. Scope and precedence must be supplied to the shared judgement.

8. The important pins are resolvable locally today, but the direction needs an explicit resolver contract.

O/pyproject.toml:69 pins D to v1.187.0. O/uv.lock:507 resolves it to b9fbb312a85d162e4d95a716a059006122ae6835. Runtime is pinned at O/pyproject.toml:70 and O/uv.lock:561 to v0.29.1 / f525a0b1d10d3c62c449c51bd3a47e54c6f4844c. Livespec's relevant compatibility pin is O/.livespec.jsonc:212-223, v0.45.1, locally resolving to 403bcfe9245e108d1055d44358f1c60b88d9c056. O/SPECIFICATION/contracts.md:10543-10559 defines that core pin's meaning.

Do not infer these pins from .mise.toml: its tools are non-Python binaries (:1-6,26-30). Do not use the stale template origin: O/.copier-answers.yml:9,15 says v0.2.0/master. O/.livespec.jsonc:156-159's cross_repo_targets entry names master for coordination, not the adopted release.

Specify declared repository identity, pin source and precedence, immutable resolved commit, spec root, retrieval caching, unavailable-source behavior and consistent snapshot use. Different upstream surfaces can have different pins: D/SPECIFICATION/spec.md:24-26 separately describes Python and workflow consumption. Resolve the applicable surface explicitly. Local tag reads prove resolution for these examples; they do not establish live forge availability or that every fleet repository has usable release pins.

9. The janitor-refresh example is narrower than the direction claims; existing clauses already authorize some “run once” behavior.

D v1.187.0 SPECIFICATION/contracts.md:561 already requires the suite-green leg to reuse a passing full pre-commit aggregate on the exact staged tree and not launch another suite. This is expressly spec-first and names the same-tree-reuse implementation owner. The preceding Scope bullet at :558 cannot be read in isolation.

That does not authorize postponing the required commit-time evidence until a later janitor aggregate. The existing reuse clause requires an earlier passing aggregate in the same commit's pre-commit hook. O/SPECIFICATION/contracts.md:3621 and :3663 separately require the janitor's full aggregate; :3661's once-per-tree rule is scoped to a successful fix turn.

Therefore keep the janitor-refresh item held until its actual acceptance criteria and riders establish the intended ordering. If it implements pre-commit same-tree reuse, existing ratification may supply a conforming route. If it skips commit-time verification and relies on the later aggregate, it needs an upstream amendment and a consumer adoption path. The title and quoted Scope bullet alone do not establish which implementation it requests. This review does not authorize releasing its live hold.

10. The asserted reuse cap is inaccurate and materially affects the cost estimate.

The ratified reuse rule is based on unchanged input and selected/named clause provenance, not a universal one-call-per-version cap: O/SPECIFICATION/contracts.md:6890. It can reuse across unrelated revisions and retake within one revision after relevant input changes.

There is also a concrete current non-feature reuse hole. O/commands/_spec_change_tier_gate.py:222-228 writes an exempt result with the default empty provenance. Before the next call, the same function computes a nonempty selected-clause set (:174-184). O/commands/_spec_change_tier_record.py:280-287 refuses reuse when that set differs from the recorded empty set. The writer still marks the empty provenance complete (:186-208).

An in-memory probe created a non_functional tier-none record through the production writer and attempted production reuse against the unchanged local tree and statement; reuse returned None. This means the quoted one-per-version cap does not protect that path even before adding foreign material.

Correct the baseline and measure actual cadence attempts, input/output usage and reuse rates across both orchestrators and adopting repositories. The supplied counts use issue type rather than judged class, and cannot independently establish B's fleet cost. This cost issue is directly relevant to choosing A versus B; it should not be hidden by a presumed cap.

11. A single model can produce the proposed answer, but correctness needs explicit semantics and measured controls.

The current class rubric defines bug as “behaviour that contradicts what is already stated” without separating the defective current state from the requested final state: O/.claude-plugin/scripts/_vendor/livespec_runtime/spec_stated.py:114-118. Merely appending “name a violated MUST” risks holding repairs because their descriptions quote the violation they fix.

Require a finding to name the requested post-change behavior, the applicable obligation with its conditions/exceptions, and a verbatim supporting quote from a body actually supplied. Validate that the evidence resolves. Preserve multiple simultaneous findings and separate conflict from missing coverage. Include binding prohibitions and inherited requirements rather than relying on a literal positive MUST token.

Before claiming equivalent reliability from one combined call, evaluate at least paired defect/repair descriptions, the janitor timing alternatives above, permitted configuration choices, scoped local refinements, mixed feature-and-contradiction items, omitted bodies, duplicate headings and unavailable pinned specs. Parser acceptance and a bounded prompt do not prove conflict detection. No model evaluation was performed in this review.

The smallest defensible Scenario 206 amendment is to change its bug-routing case to: “Given an implement-kind item classified bug whose requested resulting behavior contradicts no applicable binding requirement of its governing specifications ... Then it is routed through intake exactly as an item not subject to the tier.” Change the purpose line to preserve bugs' and chores' leeway when they do not contradict those requirements. Add the opposite case for every class, with a repository-qualified conflict citation and a mechanically enforced hold. Amend the autonomy-tier bullet in contracts.md:1571 at the same time; editing the scenario alone leaves the governing exemption intact. The cross-repository lifecycle, unavailable-input policy and shared runtime/JSONL schemas require their own coordinated clauses.

Verdict: adopt with named changes — correct B's input/cost model; replace the failing union retrieval strategy; define qualified governing sources, applicability and precedence; complete foreign proposal, ratification, pin-adoption and release handling; coordinate both consumers' schemas, runners and migration; and ratify the narrow non-feature conflict exception with measured controls. Do not adopt option B as written.
