# Research brief: best practices for preserving an AI factory run's work

You are an independent researcher for the plan `factory-run-work-preservation` in /data/projects/livespec-orchestrator-beads-fabro. The maintainer asked for "deep research into fabro/petri best practices and other ai dark factories ... to determine best practices and ideas for direction". A second researcher on a different model is doing the same job separately. Do not coordinate with it, and do not read its output.

**This is read-only research.**
- Do NOT edit any repository file.
- Do NOT write to the beads ledger.
- Do NOT start, cancel or remove any factory run.
- Do NOT push anything.
- The ONLY file you write is your output file, named at the bottom.

## Read first

tmp/frwp/context-facts.md. It holds the measured facts about how runs end today and what each ending keeps. Treat it as the starting map, but verify any fact you lean on against the source.

## Questions

1. **Fabro and Petri themselves.** Read the source and docs of the Fabro fork (/data/projects/fabro) and the Petri executor (/data/projects/petri). Check upstream docs and repositories on the web where they exist.
   - What durability mechanisms do they provide or intend for a run's git work? For example: run-branch and meta-branch push, checkpoints, `finalize_run`, conclusion diffs, run hooks (`stage_complete`, `sandbox_cleanup`), environment lifecycle `preserve`, and sandbox retention.
   - What does upstream recommend or default to?
   - Which of these could carry preservation for this factory, at what cost, and what gaps would remain? A gap would include no checkpoint for a cancelled attempt, a restart exit that does not finalize, or the k8s copy-out failure.
   - Cite file:line or URLs.

2. **Other AI software factories and coding-agent platforms.** How do they keep an agent run's work when the run is cancelled, times out, crashes or is torn down? Examples include:
   - GitHub Copilot coding agent, OpenAI Codex cloud tasks, Devin, Google Jules, Cursor background agents;
   - Factory.ai droids, OpenHands, Sweep, Amp, Sourcegraph, StrongDM's software factory / attractor (Fabro's lineage);
   - anything else credible you find.

   Look for patterns such as:
   - continuous WIP commits pushed to a branch or PR;
   - snapshotting the sandbox volume or filesystem;
   - durable-execution engines (Temporal-style) checkpointing state;
   - a separate preservation service;
   - git bundles or refs uploaded to object storage;
   - retention policies.

   Cite sources (URLs, docs, blog posts, source code), and mark anything you could not verify.

3. **General durable-execution and CI practice that applies.** Examples:
   - write-ahead or progress-before-acknowledge;
   - "no destructive operation without a durable export" enforced at one gate;
   - the outbox pattern;
   - finalizers (Kubernetes finalizers on a pod or PVC that block deletion until a preservation controller has exported);
   - pre-stop hooks;
   - CI artifact retention.

4. **Ideas for direction.** Against this factory's constraints, give 3 to 6 concrete candidate designs, including any not in (a)/(b)/(c). The constraints are:
   - agent stages may not hold a publication credential;
   - the broker writes only PR comments and proof assets;
   - the k8s copy-out fails;
   - history is rewritten by rebases;
   - endings happen outside the Dispatcher, such as a server restart or an operator rm.

   For each design, state:
   - which endings it covers and which it misses;
   - where the writer lives;
   - its credential path;
   - its cost (pushes per run, ref count, load on the forge API);
   - the retention and cleanup rule it implies;
   - what it does to the three in-flight per-path fixes (bd-ib-adcaa6 cancel-for-restart, bd-ib-vraou4 external cancel, bd-ib-ds4yrm wall-budget cancel).

   Then say which you would pick and why. That is your opinion, labelled as such.

## Output

Write ONE markdown file, at most about 2500 words, dense, with a sources list at the end. The output path is named in the launch prompt you were given; if none was given, use tmp/frwp/research-<your-model-name>.md. When the file is written, stop.
