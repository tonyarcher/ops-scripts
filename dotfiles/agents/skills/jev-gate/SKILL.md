---
name: jev-gate
description: Run atomic Jev checks before dispatching independent review
---

# Jev diff gate

Use this skill after verification passes and before dispatching the `review`
subagent. Jev returns typed judgments, never prose. The agent owns context
collection and policy. Jev only judges the evidence it receives.

## Setup

Confirm the server with `jev_models`. If it is unavailable, skip Jev and proceed
to independent review. Say that Jev was skipped. Never block on Jev.

The server pins `jev-1.14.0` through `JEV_MODEL`. Log the versioned model id from
each response. If the pin is removed, recalibrate before trusting the results.

## Build the state

Run deterministic prechecks first:

1. Include baseline-to-current changes and relevant untracked files.
2. Exclude `dist/`, `coverage/`, `node_modules/`, `build/`, and lockfiles.
3. Run the repository's canonical verification and record its exit code.
4. Scan for secrets. Redact them and report the redaction.
5. Record missing, redacted, or truncated evidence explicitly.

A failed verification, missing required evidence, or suspected secret is a
`needs-changes` result. Do not ask Jev to excuse it.

Send named fields: `requirements`, `changed_files`, `diff`, `tests_added`,
`verification`, and `evidence_gaps`.

## Ask one batched call

Use one `jev_ask` with independent `check` questions. Phrase each problem check
so `yes` means the problem exists.

- `requirements-covered`: the diff implements every stated requirement.
- `tests-cover-change`: the added tests cover the changed behavior.
- `scope-creep`: the diff contains changes unrelated to the request.
- `unsafe-change`: the diff weakens safeguards around secrets, authentication,
  destructive operations, or production configuration.
- `obvious-regression`: the diff contains a concrete breakage in an existing
  behavior.

Give each check concrete `yes_means` and `no_means` criteria. Use
`yes_at_or_above: 0.7` and `no_at_or_below: 0.3`. The middle band is `uncertain`.
`jev_ask` returns the raw `noul` probability; compute the verdict in code rather
than depending on a `verdict` field.

## Map the verdict in code

Apply this table after reading the returned probabilities:

| Condition                             | Verdict         |
| ------------------------------------- | --------------- |
| Any problem check is `yes`            | `needs-changes` |
| Any required positive check is `no`   | `needs-changes` |
| Any check is `uncertain`              | `abstain`       |
| All checks are settled and acceptable | `approve`       |

- `approve`: dispatch the `review` subagent.
- `needs-changes`: fix, re-verify, and ask again.
- `abstain`: ask the user. Do not guess.

An `approve` only permits independent review. It never permits a commit.

Log the model id, each probability, each verdict, and the final gate verdict.
