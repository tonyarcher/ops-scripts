# AGENTS.md

This is a personal ops toolbox, not an application. Tens to ~100 small scripts: importers, cron jobs, and data tools for sites that do not ship the admin features we need. Agents should add a script in the right folder, keep it self-contained, and leave unrelated scripts alone.

Read `README.md` for the human-facing layout. This file is the working contract for coding agents.

## What belongs here

- Importers and sync jobs that pull or push data into a site (Mastodon, etc.).
- Cron-style maintenance: cleanup, reports, scheduled follows/syncs.
- One-off or repeatable data manipulation (CSV/JSON/SQL dumps, transforms).
- Thin admin CLIs for a product that has no decent UI for the job.

Do not turn this repo into a web app, monorepo product, or shared framework. No extra packages, CI, or sample scripts unless the user asks.

## Language policy

Pick the language from the job, not from habit.

| Job | Language | How to run |
| --- | --- | --- |
| Loading, scraping, or manipulating a website / HTTP API | TypeScript on Bun or Node ≥23.6 native TS | `bun run path/to/script.ts` or `node path/to/script.ts` |
| Local files, data munging, reports that never leave the box | Python 3 | `python path/to/script.py` |
| SSH, remote shells, server glue, cron wrappers | Python 3, or a small POSIX `sh`/`bash` script if it is genuinely just glue | `python …` or `./script.sh` |
| Windows services, PnP, audio, other Win32 admin | PowerShell 5.1+ under `windows/` | `powershell -File windows/scripts/…` |

Rules:

- New website/API work is TypeScript. Prefer Bun; Node native TS is an accepted runner. Do not add ts-node, tsx, Deno, Kotlin, or a second HTTP library for that.
- New local-only or SSH work is Python. Prefer the stdlib. Add a dependency only when stdlib is painful.
- Shell is for wrappers, cron entries, and `ssh` one-liners — not for parsing HTML or calling JSON APIs.
- Windows-only work lives in `windows/`. Do not put `.ps1` files in `cron/`, `importers/`, `data/`, `sites/`, or `dotfiles/`. Those trees are Linux/WSL or OS-agnostic.

### Bun / TypeScript

- One `.ts` file is enough for most jobs. Use a directory when there is sample input, a local `package.json`, or notes.
- Prefer Bun's built-in `fetch`, `Bun.file`, and `bun:sqlite`. Do not add axios, node-fetch, or a bundler. When targeting Node, Node built-ins are fine too (`node:sqlite`, `node:test`, `fetch`).
- TypeScript, not JavaScript. Keep types local and boring; no `any` to silence real mistakes.
- Shared TS helpers go in `lib/` (e.g. `lib/http.ts`). Import with a relative path. Do not invent a workspace package until several scripts actually share the code.
- Shebang optional: `#!/usr/bin/env bun`. Document the `bun run …` command in the header comment either way.
- Rate-limit remote calls. Sleep between writes. Fail loud on non-2xx unless the script is explicitly probing.
- Never log access tokens. Read them from the environment.

### Python

- Target current CPython 3. Target the stdlib first (`pathlib`, `json`, `csv`, `subprocess`, `argparse`, `urllib` only if you must — prefer not using Python for HTTP).
- If the job is SSH or remote shell, use `subprocess` with an explicit argv list, never `shell=True` with interpolated strings.
- Shared Python helpers go in `lib/` (e.g. `lib/sshutil.py`).
- No `requirements.txt` for a one-file stdlib script. If a script truly needs a package, put a pinned `requirements.txt` next to that script only.
- Header comment plus `argparse` (or a few `sys.argv` checks) so a human can run it without reading the whole file.

## Layout

Group by job type, then product, then script name:

```
bin/          optional PATH wrappers / one-liners
lib/          shared helpers used by more than one script
cron/         jobs meant to run on a schedule
importers/    pull or push data into external sites
data/         one-off transforms, reports, cleanup
sites/        ad-hoc admin tools grouped by product
config/       example configs only — never real secrets
docs/         longer notes when a README section is not enough
dotfiles/     shell dotfiles + installer (bash/, setup.sh) for Ubuntu/WSL
windows/      Windows-only admin scripts (PowerShell). Do not mix Linux/agnostic work here.
```

Examples:

- `importers/mastodon/follow-hashtags/follow-hashtags.ts`
- `cron/mastodon/prune-old-media.py`
- `data/normalize-export.py`
- `sites/mastodon/list-filters.ts`

Conventions:

- kebab-case names.
- One directory per script when it has extras. A lone file is fine for a true one-liner.
- Each script must be runnable on its own. Shared code lives in `lib/`, not copy-pasted.
- Prefer a short header comment over a per-script README unless usage is non-obvious.
- Config examples go in `config/examples/`. Real values stay in an untracked `.env` or the process environment.

## Adding a script

1. Choose `importers/`, `cron/`, `data/`, or `sites/` from the job type. Windows-only jobs go in `windows/scripts/` instead.
2. Put it under the product name when it is site-specific (`mastodon/`, …).
3. Follow the language policy above.
4. Add a 5–15 line header: what it does, how to run it, required env vars, anything that can destroy data.
5. Read secrets from the environment. Add placeholders to `config/examples/.env.example` if they are new.
6. Do not add a root `package.json`, linter, test harness, or framework “for later.”
7. Do not rewrite neighboring scripts to match the new one.

## Secrets and safety

- Never commit tokens, cookies, private keys, `.env` files, or production dumps.
- `.gitignore` already drops `.env`, `.env.*`, `*.local.*`, `.idea/`, and local `tmp/` / `var/`. Keep it that way.
- Default to dry-run or a limit flag when a script writes to a remote site or deletes data.
- Be a good guest: timeouts, retries with backoff, and a delay on bulk writes. No unbounded scrape loops.
- Do not print secrets, even in debug output.
- Do not open or attack systems the user did not name. These scripts run against the user's own sites and accounts.

## What not to do

- Do not add npm toolchains, ts-node, or tsx. Bun or Node native TS runs the TypeScript.
- Do not introduce Kotlin, Gradle, or Maven for new work.
- Do not create empty sample scripts to “fill out” the tree.
- Do not add CI, Docker, or a monorepo workspace unless asked.
- Do not commit `node_modules/`, `.venv/`, or IDE junk.
- Do not expand scope past the script the user asked for.

## Verification

There is no repo-wide test suite. Before finishing:

- The new or changed script is in the right folder and named in kebab-case.
- It runs the way the header says (`bun run …` or `python …`).
- `node --test` passes for scripts that have tests.
- No secrets landed in the diff.
- Existing scripts you did not need were not touched.
