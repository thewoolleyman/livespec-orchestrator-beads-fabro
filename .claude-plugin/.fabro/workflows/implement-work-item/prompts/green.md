# Green stage — implement against the Red handoff

You are the Green node of a separate Red/Green implementation flow.
The complete work-item goal is in the Fabro-injected `Goal:` preamble.
Read the work item's Definition of Done, the repository instructions, and the
handoff file before changing anything. Resolve the handoff path with:

    git rev-parse --git-path livespec-implement-handoff.md

Read the handoff file in full, including the Red section and any declared
already-satisfied outcome.

1. Make the Red test pass by changing implementation files only. Never change the Red test file.
2. Run only the tests your change touches. Do not make a commit.
3. Before ending, run

       "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-implement-gate-preview.py" green

   to preview the checks the Green commit will run over its staged change. Fix
   every failed target the preview names that is within this turn's scope, then
   run the preview again after each fix. The preview does not decide whether a
   commit succeeds.
4. Append, never rewrite an earlier section, using a `## green` section that
   states what changed, which tests ran, and the exit status and failed target
   names of the last gate preview run. If no preview ran, state that and why.

If the Red test is wrong, do not change it. Append, never rewrite an earlier
section, a `## test-wrong` section with a declared `test-wrong` outcome and its reason,
then end the turn with that declared `test-wrong` outcome and its reason.

The handoff is append-only: append your new section to the resolved file and
never rewrite an earlier section.
