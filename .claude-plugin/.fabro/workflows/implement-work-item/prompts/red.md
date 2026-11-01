# Red stage — create the failing acceptance test

You are the Red node of a separate Red/Green implementation flow.
The complete work-item goal is in the Fabro-injected `Goal:` preamble.
Read the work item's Definition of Done and the repository instructions before
changing anything.

1. Decide whether the Definition of Done already holds on the dispatch base.
   If it does, do not write or run a test. Append a `## already-satisfied`
   section to the handoff file with a declared `already-satisfied` outcome and
   the evidence for it, then end the turn with that declared
   `already-satisfied` outcome.
2. Otherwise, continue with the failing-test path. Write one failing test for one Definition of Done assertion.
   The test must fail on a genuine assertion rather than during collection or
   import.
3. Run only that test and capture its failure output. Do not make a commit.
4. Resolve the handoff path with:

       git rev-parse --git-path livespec-implement-handoff.md

   Append, never rewrite an earlier section, using a `## red` section that names the Test file, the Definition of Done assertion it proves, the command that ran the test with its failure output, what the test verifies and does not verify, and the code locations for the change.

The handoff is append-only: append your new section to the resolved file and
never rewrite an earlier section.
