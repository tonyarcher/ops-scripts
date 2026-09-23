---
name: jev-triage
description: Set review depth with one fast Jev triage call over the diff
---

# Jev triage

Use this skill at the start of a review task, before the deep read.
Jev is a decision-only model. It returns typed answers, never prose.
The agent owns context collection. Jev only judges the bundle it
receives. Never use Jev to generate fixes or review prose. Never use
it for deep reasoning. It scores options defined in code. It cannot
invent one.

## Enable Jev

Neither Zen chat path is verified working. `opencode/jev-1.13-free`
500s on chat-style calls (opencode logs, 3 title sessions, 2026-09-19);
`opencode/jev-1.13` and `jev-latest` are untested there — catalog marks
Jev `tool_call: false`. Do not set any Jev id as `small_model` or an
agent model without a passing smoke test first.

Working path: typed tools (`jev_ask`, `jev_models` through `jev-mcp`,
`enabled: false` in the seed) with a TypeSafe key:

1. Get a key from `https://console.typesafe.ai/settings/keys`.
2. Provide it without committing it. Preferred order:
    - `~/.config/typesafe/key` file, mode `600`. Most reliable.
    - Exported `TYPESAFE_API_KEY` in the process that launches OpenCode.
3. Flip `enabled` to `true` in the OpenCode config. Reload the session.
4. Run `jev_models`. A working key lists model ids.

Do not add an `environment` block with an empty key. An empty string
shadows the key-file fallback and turns a working setup into a
missing-key error.

If neither path is live, skip Jev and review by
reading. Say that Jev was skipped.

## Build the triage bundle

Send only the bounded context the decision needs. Reuse the
`jev-gate` bundle rules: baseline-to-current changes with relevant
untracked source and docs, excluding `dist/`, `coverage/`,
`node_modules/`, `build/`, and lockfiles. Redact secrets. Report
redaction explicitly. Attach requirements and verification output so
the requirements check has evidence.

Missing, redacted, or truncated evidence stays visible in the result.
Never treat missing evidence as clean.

## Ask one batched call

Prefer a single `jev_ask` call. Extra questions add almost no latency
or cost. Define the option set in code. Questions cannot see each
other. State speculative premises explicitly.

- Classify `verdict`: `approve`, `needs-changes`, `abstain`.
- Score `risk`: ordered levels `low`, `medium`, `high`.
- Check `requirements-met`: yes or no with probability.
- Score `complexity`: ordered levels `simple`, `involved`, `deep`.

Keep thresholds in code. Defaults are `act_above: 0.8` and
`review_above: 0.5` for choice and score, `yes_at_or_above: 0.7` and
`no_at_or_below: 0.3` for checks. Calibrate on what a wrong call costs.

## Map the action

- Low risk with requirements met and confident: quick pass, then read
  the flagged files only.
- Anything else: full read of the diff and the surrounding code.
- `abstain` or `uncertain`: escalate to the user. Do not guess.
- Log the versioned model id from the response, not the alias.
