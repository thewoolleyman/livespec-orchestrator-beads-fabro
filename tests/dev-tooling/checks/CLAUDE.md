# tests/dev-tooling/checks/

Per-check tests for the impl-beads-private enforcement scripts under
`dev-tooling/checks/`. Each `test_<name>.py` covers BOTH the pass and the
fail cases of the corresponding `dev-tooling/checks/<name>.py` `main()`.

Conventions:

- The check module is loaded via `importlib.util.spec_from_file_location`
  (it lives outside the pytest `pythonpath`'s package roots) and its
  `main()` invoked directly.
- Store-backed checks drive the in-memory `FakeBeadsClient` hermetically:
  set `LIVESPEC_BEADS_FAKE=1`, reset the store's process-singleton fake per
  test, seed via `append_work_item`, and monkeypatch the git-reachability
  seam so no real `git` runs. An empty tenant is the trivial-pass fixture.
- `monkeypatch.chdir(tmp_path)` isolates cwd-relative reads (`.livespec.jsonc`
  / the resolved store descriptor) so a happy-path run never touches the
  repo working tree.
