---
name: jev-route
description: Pick a task handler with one fast Jev routing call
---

# Jev route

Use this skill when the next handler is ambiguous. Jev selects from options the
agent defines. It cannot invent a handler or write a plan.

## Setup

Confirm the server with `jev_models`. If it is unavailable, route by rule:
locate-only work goes to `explore`, design goes to `plan`, implementation goes to
`build`, a behavior check goes to `review`, and destructive or ambiguous work
escalates to the user. Say that Jev was skipped.

## Build the state

Send only the evidence that separates the candidate handlers:

1. State the request in one or two sentences.
2. List each candidate handler with a concrete description.
3. Include relevant file paths, constraints, and destructive effects.
4. Redact secrets and report the redaction.

## Ask one batched call

Use one `jev_ask`:

- Classify `handler` from the candidate set. Include `answer-directly` when a
  conversational answer is valid and `human` when escalation is valid. Set
  `add_none: false` because one candidate must apply.
- Check `human-required`: the request needs a person because it is destructive,
  ambiguous, or outside the agent's authority.
- Check `prose-suffices`: the request can be answered without editing files or
  dispatching a subagent.

Use `act_above: 0.8` and `review_above: 0.5` for the choice. Use
`yes_at_or_above: 0.7` and `no_at_or_below: 0.3` for the checks. `jev_ask` returns
raw `noul` probabilities; compute `yes`, `no`, or `uncertain` in code.

## Map every answer

Apply these rules in order:

1. `human-required` is `yes` or `uncertain`: escalate to the user.
2. `prose-suffices` is `yes`: answer directly.
3. The chosen handler is `human`: escalate to the user.
4. The handler action is `act`: dispatch it.
5. The handler action is `review`: dispatch it with a note naming what it must
   verify.
6. The handler action is `abstain`: escalate to the user.

An `uncertain` `prose-suffices` result does not override a clear handler choice.
Report it in the dispatch note.

Log the versioned model id, the chosen handler, its probability, and both check
probabilities.
