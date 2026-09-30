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

Keep thresholds in code. Defaults are `act_above: 0.8` and
`review_above: 0.5` for choice and score, `yes_at_or_above: 0.7` and
`no_at_or_below: 0.3` for checks. Calibrate on what a wrong call costs.

## Map the action

- `act` with `approve`: proceed to the `review` subagent.
- `review` or `needs-changes`: fix, re-verify, and ask again.
- `abstain` or `uncertain`: escalate to the user. Do not guess.
- Log the versioned model id from the response, not the alias.
