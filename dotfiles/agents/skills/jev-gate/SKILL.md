---
name: jev-gate
description: Run the Jev diff gate before declaring implementation done
---

# Jev diff gate

Use this skill at the end of an implementation task, after verification
passes and before dispatching the `review` subagent. Jev is a
decision-only model. It returns typed answers, never prose. The agent
owns context collection. Jev only judges the bundle it receives.

## Enable the server

`jev-mcp` ships `disabled: true` in the OpenCode config seed. It needs
a key.

1. Get a key from `https://console.typesafe.ai/settings/keys`.
2. Provide it without committing it. Preferred order:
   - `~/.config/typesafe/key` file, mode `600`. Most reliable.
   - Exported `TYPESAFE_API_KEY` in the process that launches OpenCode.
3. Flip `disabled` to `false` in the OpenCode config. Reload the session.
4. Run `jev_models`. A working key lists model ids. Stop here if it errors.

Do not add an `environment` block with an empty key. An empty string
shadows the key-file fallback and turns a working setup into a
missing-key error.

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
