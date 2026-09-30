---
name: jev-gate
description: Run the Jev diff gate before declaring implementation done
---

# Jev diff gate

Use this skill at the end of an implementation task, after verification
passes and before dispatching the `review` subagent. Jev is a
decision-only model. It returns typed answers, never prose. The agent
owns context collection. Jev only judges the bundle it receives. Never
use Jev to write code, prose, or plans. Never use it for deep reasoning.

## Setup

Setup is not restated here. It lives in the user-wide `AGENTS.md` under
**Jev → Set up Jev**. Confirm the server is live with `jev_models`; a working
key lists model ids.

If the server is not live, skip Jev and proceed to the `review` subagent
without it. Say that Jev was skipped. Never block on Jev.

## Build the context bundle

Send only the bounded context the decision needs.

1. Snapshot the baseline first when the task did not record one.
2. Collect baseline-to-current changes, including relevant untracked
   source and docs.
3. Exclude `dist/`, `coverage/`, `node_modules/`, `build/`, and lockfiles.
4. Redact secrets. Report redaction explicitly.
5. Attach requirements, tests added, and verification output.
6. State speculative premises explicitly. Questions cannot see each other.

Missing, redacted, or truncated evidence stays visible in the result.
Never treat missing evidence as clean.

## Ask one batched call

Prefer a single `jev_ask` call. Extra questions add almost no latency
or cost. Define the option set in code. Jev can pick the wrong option
but can never invent one.

- Classify `verdict`: `approve`, `needs-changes`, `abstain`.
- Score `risk`: ordered levels `low`, `medium`, `high`.
- Check `requirements-met`: yes or no with probability.

Keep thresholds in code. For this gate the defaults are `act_above: 0.55`
and `review_above: 0.3` for choice and score, `yes_at_or_above: 0.7` and
`no_at_or_below: 0.3` for checks.

Provisional, derived from one observed call on 2026-09-29 (verdict
confidence 0.34, choose approve 0.56 / needs-changes 0.43, jev 1.13.0). The
check thresholds behaved (0.71 and 0.90 both landed as `yes`) and are
unchanged.

Note what actually unblocked that call: the mapping below, not these numbers.
The old action-driven rules escalated a low-confidence `approve` whatever the
thresholds said. Under the table the action column is outcome-irrelevant, so
the thresholds now mostly decide which action is reported. Fix the mapping
before tuning a threshold, and log the confidence and choice so the numbers
can be re-derived from a real sample.

## Map the action

Read the two returned fields separately. `action` is the confidence gate the
tool applied (`act`, `review`, `abstain`). The chosen option is what the model
actually picked. The option decides proceed versus fix. This table is for the
`verdict` question; its options are `approve`, `needs-changes`, `abstain`.

| chosen option   | `act`    | `review` | `abstain` |
| --------------- | -------- | -------- | --------- |
| `approve`       | proceed  | proceed  | proceed   |
| `needs-changes` | fix      | fix      | fix       |
| `abstain`       | escalate | escalate | escalate  |

- proceed: dispatch the `review` subagent.
- fix: fix, re-verify, and ask again.
- escalate: ask the user. Do not guess.

A low-confidence `approve` still goes to the reviewer, because the reviewer is
the real backstop and nothing reaches a commit without it.

Checks return `yes`, `no`, or `uncertain`. A `no` counts as `needs-changes`.
An `uncertain` check is reported in the summary but does not block on its own.

Log the versioned model id from the response, not the alias.
