---
topic: sandbox-driver-exec-keeps-command-and-credentials-out-of-the-req
author: claude-opus-5-5
created_at: 2026-10-24T01:34:53Z
---

## Proposal: sandbox-exec-stream-carries-command-and-credentials

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add a bullet to constraints.md §"Factory sandbox credential constraints" requiring every sandbox driver the factory uses (Docker, Kubernetes, or any later backend) to deliver a command's program, arguments and environment, projected credentials included, through the exec session's input stream rather than the exec request URL. The request that opens the exec session MUST NOT grow with the command's size, no credential value may appear in a request URI, a command's own standard input MUST pass through unchanged, and a transport failure without an HTTP status MUST report its underlying error text. Two scenarios inside the existing Scenario 18 state the behaviour.

### Motivation

The ratified text never addresses how a sandbox driver carries a command into the sandbox. §"Factory sandbox credential constraints" governs credential CAPABILITY and contracts.md governs credential PROJECTION (an ephemeral installation token, never the durable key), but nothing governs TRANSPORT exposure, so a projection that is correct by every current rule can still put every credential into a logged URL. That section is the generalization target and the new clause lands in it. Measured 2026-10-23 on gmktec production (Fabro 0.393.0-nightly.1, Kubernetes sandbox-driver plugin v0.4.0), run 01M5N2W7TNBCEB0M4BFCMQSMXM for livespec-dev-tooling-u2dyce passed every pod check, resolved 37 environment keys, and then failed at run_prepare_28 with "script exited with status -1"; the worker log reads "starting a command in the sandbox: reaching the Kubernetes API failed". Kubernetes exec carries every argv element as a `command=` query parameter, and the plugin wraps the environment into argv, so the 37 entries alone encode to about 28 KB of query string on every exec. Prepare steps 1 to 27 produced URLs of at most about 37 KB and succeeded; steps 28 to 31 carry the GitHub-refresh bundle inline as 48 KB base64 chunks, producing URLs of about 74 to 83 KB, and the first of them failed. The same steps pass under the Docker driver, whose exec has no URL. The plugin's own file-write path already streams over stdin for exactly this reason. The second defect has the same mechanism: every exec puts CLAUDE_CODE_OAUTH_TOKEN, GITHUB_TOKEN, CODEX_AUTH_JSON and the other run credentials into the request URI, which kube-apiserver audit logging and proxy access logs record. Work-item bd-ib-xwqn23 carries the plugin fix; this proposal states the driver-independent guarantee the factory relies on, so the next driver is bound by it as written.

### Proposed Changes

Two coordinated edits. Both MUST land together in a single revision.

**1. `SPECIFICATION/constraints.md` §"Factory sandbox credential constraints".** Insert one new bullet at the end of the bulleted list, immediately after the bullet that begins "**Withheld capability is a per-item eligibility fact, not a whole-item verdict.**" and ends "so the portion the sandbox can publish is not refused along with the portion it cannot." and immediately before the paragraph that begins "**Verification.** For each capability withheld under this section". The new bullet reads:

```
- **A command's program, arguments and environment reach the sandbox
  through the exec stream, never through the exec request URL.** A
  "sandbox driver" here means any execution backend the factory uses to
  start a command inside a factory sandbox on the engine's behalf (a
  Docker driver, a Kubernetes driver, or any later one). Every sandbox
  driver the factory uses MUST deliver each command's program, its
  arguments and its environment entries, including every projected
  credential, through the exec session's input stream, or through a file
  the driver writes over that stream before the command starts. A driver
  MUST NOT carry any of them in the URL, query string or other request
  line of the call that opens the exec session. Two properties follow
  and both are REQUIRED: the length of that request MUST NOT grow with
  the size of the command's program, arguments or environment values, so
  a large prepare step is not bounded by any proxy or API-server URL
  limit; and no credential value appears in a request URI, which is what
  API-server audit logs and proxy access logs record. A command that
  reads its own standard input MUST still receive that input unchanged
  after the driver's framing. When a driver fails to open an exec session
  without an HTTP status, its error MUST carry the underlying transport
  error text rather than only a generic "could not reach the API"
  message. A driver observed placing a credential value in an exec
  request URL is a violation of this section regardless of whether the
  run subsequently succeeded.
```

**2. `SPECIFICATION/scenarios.md` §"Scenario 18 — Dispatcher projects a non-rotatable subscription credential into a worker sandbox".** Inside that section's single fenced `gherkin` block, after its last line ("And no refresh performed or attempted inside the sandbox invalidates the host's or any peer worker's credential for any provider") and before the closing fence, insert:

```gherkin

Scenario: A sandbox driver delivers a large command and the projected credentials through the exec stream
  Given a factory sandbox driver that opens exec sessions over a request URL
  And a command whose single argument is 200000 bytes and whose environment holds 40 entries of 1000 bytes each, including the projected Claude and GitHub credentials
  When the driver starts that command inside the sandbox
  Then the request that opens the exec session is under 8192 bytes long
  And no argument value and no environment value appears in that request URL
  And the command runs inside the sandbox with exactly that argument and that environment

Scenario: A command that reads standard input still receives it after the driver's framing
  Given a factory sandbox driver that delivers program, arguments and environment through the exec stream
  When the driver starts a command that forwards its own standard input
  Then the command receives the caller's standard input byte for byte, with none of the driver's framing in it
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
