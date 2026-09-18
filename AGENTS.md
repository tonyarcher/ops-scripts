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

Pick Python first. TypeScript is only for browser view manipulation.

| Job | Language | How to run |
| --- | --- | --- |
| Website / HTTP API, scrapers, importers, servers | Python 3 (stdlib `urllib`, `http.server`, `sqlite3`) | `python path/to/script.py` |
| Local files, data munging, reports that never leave the box | Python 3 | `python path/to/script.py` |
| SSH, remote shells, server glue, cron wrappers | Python 3, or a small POSIX `sh`/`bash` script if it is genuinely just glue | `python …` or `./script.sh` |
| Browser view manipulation only (DOM) | TypeScript | `node path/to/script.ts` |
| Windows services, PnP, audio, other Win32 admin | PowerShell 5.1+ under `windows/` | `powershell -File windows/scripts/…` |

Rules:

- New website, API, importer, and server work is Python. Use stdlib `urllib`, `http.server`, and `sqlite3` first. Add a dependency only when stdlib is painful, with a pinned `requirements.txt` next to that script.
- TypeScript is only for browser view manipulation (DOM). Do not write Node servers, importers, or HTTP clients for new work.
- New local-only or SSH work is Python. Prefer the stdlib. Add a dependency only when stdlib is painful.
- Shell is for wrappers, cron entries, and `ssh` one-liners — not for parsing HTML or calling JSON APIs (use Python for that).
- Windows-only work lives in `windows/`. Do not put `.ps1` files in `cron/`, `importers/`, `data/`, `sites/`, or `dotfiles/`. Those trees are Linux/WSL or OS-agnostic.

`windows/scripts/install-tools.ps1` (and `dotfiles/setup.sh --install-tools`, `macos/Brewfile`) also install review CLIs: gitleaks, osv-scanner, ast-grep, git-delta.

### TypeScript (browser views only)

- TypeScript exists here only for browser view manipulation (DOM). Do not use it for servers, importers, or HTTP clients.
- TypeScript, not JavaScript. Keep types local and boring; no `any` to silence real mistakes.
- Rate-limit remote calls. Sleep between writes. Fail loud on non-2xx unless the script is explicitly probing.
- Never log access tokens. Read them from the environment.

### Python

- Target current CPython 3. Type hints on every public function. `from __future__ import annotations`.
- Target the stdlib first (`pathlib`, `json`, `csv`, `subprocess`, `argparse`, `urllib`, `http.server`, `sqlite3`).
- HTTP servers use stdlib `http.server` (or `ThreadingHTTPServer`). HTTP clients use `urllib`. Rate-limit remote calls, retry with backoff, set timeouts. Never log tokens.
- If the job is SSH or remote shell, use `subprocess` with an explicit argv list, never `shell=True` with interpolated strings.
- Lint: `ruff check` / `ruff format`. Complexity `C901` ≤ 15; functions ≤ ~30 lines. `mypy --strict` when the script is more than a one-liner.
- Shared Python helpers go in `lib/` (e.g. `lib/sshutil.py`).
- No `requirements.txt` for a one-file stdlib script. If a script truly needs a package, put a pinned `requirements.txt` next to that script only.
- Header comment plus `argparse` (or a few `sys.argv` checks) so a human can run it without reading the whole file.
- Go or Rust only for a compiled binary / real concurrency need, never for a new importer. No Kotlin/Gradle in this repo.

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

- `importers/mastodon/follow-hashtags/follow_hashtags.py`
- `cron/mastodon/prune-old-media.py`
- `data/normalize-export.py`
- `sites/mastodon/list-filters.py`

Conventions:

- kebab-case names.
- One directory per script when it has extras. A lone file is fine for a true one-liner.
- Each script must be runnable on its own. Shared code lives in `lib/`, not copy-pasted.
- Prefer a short header comment over a per-script README unless usage is non-obvious.
- Config examples go in `config/examples/.env.example`. Real values stay in an untracked `.env` beside the script or in the process environment. User-wide secret rules apply (never commit/push `.env`).

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
- CLIs: human stdout, `error:` on stderr. Long-running daemons follow user-wide JSON logging (`ts`, `level`, `msg`, `service`). Never log tokens.
- Do not open or attack systems the user did not name. These scripts run against the user's own sites and accounts.

## What not to do

- Do not write Node servers, importers, or HTTP clients. TypeScript is only for browser view manipulation.
- Do not add npm toolchains, ts-node, or tsx for server or importer work.
- Do not introduce Kotlin, Gradle, or Maven for new work. User-wide JVM rules do not apply here.
- Do not create empty sample scripts to “fill out” the tree.
- Do not add CI, Docker, or a monorepo workspace unless asked.
- Do not commit `node_modules/`, `.venv/`, or IDE junk.
- Do not expand scope past the script the user asked for.

## Verification

There is no repo-wide test suite. Before finishing:

- The new or changed script is in the right folder and named in kebab-case (Python modules use `snake_case` so they import).
- It runs the way the header says (`python …`).
- `python -m unittest` (or `python path/to/test_*.py`) passes for scripts that have tests.
- `ruff check`, `ruff format --check`, and `mypy --strict` pass for changed Python files.
- No secrets landed in the diff.
- Existing scripts you did not need were not touched.
