"""Thin-transport command entry points for livespec-orchestrator-beads-fabro.

Each public-facing slash command (`list-work-items`, `next`)
has a Python module here with a `main()` function returning an integer
exit code. The corresponding wrapper at
`.claude-plugin/scripts/bin/<skill>.py` bootstraps sys.path and invokes
`main()`.

Per SPECIFICATION/constraints.md §"Skill orchestration constraints",
thin-transport SKILL.md files MUST NOT accrete orchestration logic — all
behavior lives here in the Python module.
"""
