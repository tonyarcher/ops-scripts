---
name: jev-triage
description: Rank changed files for review with the Jev batch triage tool
---

# Jev review triage

Use this skill before the deep review read. It sets review order and depth. It
does not replace reading the full diff and the surrounding code.

## Setup

Confirm the server with `jev_models`. If it is unavailable, review by reading.
Say that Jev was skipped. This skill requires `jev-mcp` 0.5.0 or later because it
uses `jev_triage`.

## Build the items

1. Enumerate changed files, including relevant untracked source and docs.
2. Exclude `dist/`, `coverage/`, `node_modules/`, `build/`, and lockfiles.
3. Scan for secrets before sending file contents.
4. Use `path` only for clean files below the server's allowed roots.
5. If a file needs redaction, pass the redacted content as `text` instead.
6. Keep each item focused on one file. Split batches above 50 items.

Never route around a denied path or a refused credential file. A file access
error means the file was not judged.

Send the requirements and verification summary as context in each question or
in a structured `text` item. Questions in one request cannot see one another.

## Ask one batch per group

Use `jev_triage` with these questions for every item:

- `requirements-relevant`: the file contains changes relevant to the stated
  requirements.
- `risk`: review risk on three concrete levels.
    - `0`: docs, tests, comments, or isolated local behavior.
    - `1`: application logic, API behavior, concurrency, or error handling.
    - `2`: authentication, secrets, schema migration, destructive data operations,
      or production configuration.
- `complexity`: review complexity on three concrete levels.
    - `0`: one local change with direct evidence.
    - `1`: several call sites or moderate control flow.
    - `2`: cross-module behavior, protocol changes, or subtle invariants.

Use `act_above: 0.8` and `review_above: 0.5` for scores. Use
`yes_at_or_above: 0.7` and `no_at_or_below: 0.3` for the check. Compute the check
verdict from the raw `noul` probability; do not depend on a `verdict` field.

## Route the review

Read every item's `answers` or `error` before choosing a review path.

- Any item error: read that file manually.
- `risk` at or above 2, or `complexity` at or above 2: full read.
- `requirements-relevant` is `no` or `uncertain`: full read to confirm scope.
- Low risk, simple complexity, and relevant `yes`: quick pass, then read the
  surrounding code for any flagged behavior.
- Anything else: full read.

Rank files by `risk`, then `complexity`, and read the highest first. Low risk is
not permission to skip a changed file.

Log the versioned model id, item scores, check probabilities, failures, and the
resulting review order.
