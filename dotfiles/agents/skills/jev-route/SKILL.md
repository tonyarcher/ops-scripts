---
name: jev-route
description: Pick the handler for a task with one fast Jev routing call
---

# Jev route

Use this skill when the next step is ambiguous: which agent, tool,
or handler owns the task. Jev is a decision-only model. It returns
typed answers, never prose. The agent owns context collection. Jev
only judges the bundle it receives. Never use Jev to write code,
prose, or plans. Never use it for deep reasoning. It picks from
options defined in code. It cannot invent one.

## Setup

Setup is not restated here. It lives in the user-wide `AGENTS.md` under
**Jev → Set up Jev**. Confirm the server is live with `jev_models`; a working
key lists model ids.

If the server is not live, skip Jev and route by
rule: locate-only work goes to `explore`, design goes to `plan`,
implementation goes to `build`, a behavior check goes to `review`,
and destructive or ambiguous work escalates to the user. Say that
Jev was skipped.

## Build the routing bundle

Send only the bounded context the decision needs.

1. State the request in one or two sentences.
2. List each candidate handler with one line on what it does:
   deterministic code, `explore`, `plan`, `build`, `review`, or human.
3. Attach only the evidence that separates the candidates.
4. Redact secrets. Report redaction explicitly.

## Ask one batched call

Prefer a single `jev_ask` call. Extra questions add almost no latency
or cost. Questions cannot see each other. State speculative premises
explicitly.

- Classify `handler`: one option per candidate. Jev can pick the
  wrong option but can never invent one.
- Check `needs-specialist`: yes or no with probability. Catches work
  that looks routine but needs deep reasoning or a human.
- Check `prose-suffices`: yes or no with probability. A yes points
  away from dispatching an agent at all.

Keep thresholds in code. Defaults are `act_above: 0.8` and
`review_above: 0.5` for choice and score, `yes_at_or_above: 0.7` and
`no_at_or_below: 0.3` for checks. Calibrate on what a wrong call costs.

## Map the action

- `act` with the handler: dispatch it.
- `review` or low confidence: dispatch with a note on what to verify.
- `abstain` or `uncertain`: escalate to the user. Do not guess.
- Log the versioned model id from the response, not the alias.
