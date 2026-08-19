# ops-scripts

A growing collection of admin scripts for the sites and tools the owner relies on — data manipulation tools, cron jobs, and importers for sites that don't ship the admin tools we need. It started with a Mastodon hashtag importer.

## Layout

```
bin/          optional PATH wrappers / one-liners
lib/          shared helpers reused by more than one script
cron/         jobs meant to run on a schedule
importers/    pull or push data into external sites
data/         one-off transforms, reports, cleanup
sites/        ad-hoc admin tools grouped by product
config/       example configs only — never real secrets
docs/         longer notes when a README section is not enough
dotfiles/     shell dotfiles + installer (bash/, setup.sh) for Ubuntu/WSL
```

## Conventions

These are meant to scale to ~100 scripts:

- Group by job type first (`cron` / `importers` / `data` / `sites`), then by product (`mastodon`, …), then by script name.
- One directory per script when it has extras (sample input, notes). A lone file is fine for a true one-liner.
- kebab-case names.
- Each script should be runnable on its own; put shared code in `lib/`.
- Website / API work: TypeScript on Bun (`bun run path/to/script.ts`) or Node ≥23.6 native TS (`node path/to/script.ts`).
- Local files, reports, SSH, and shell glue: Python 3 (`python path/to/script.py`).
- Secrets via environment variables or an untracked `.env` — never committed.
- Prefer a short comment block at the top of a script over a separate README unless usage is non-obvious.

## Adding a script

1. Pick the directory that fits the job type (see Layout).
2. Create `product/script-name/` if it needs extras, or just a single kebab-case file.
3. Keep it self-contained; move any reused logic into `lib/`.
4. Read config from env vars or `.env`, never hardcode secrets.
5. Add a short header comment describing what it does and how to run it.
6. If it needs a config example, add it under `config/examples/`.

## Running scripts

```
node path/to/script.ts
bun run path/to/script.ts
python path/to/script.py
```

New site work should be TypeScript (Bun or Node native TS).

Agents: see `AGENTS.md`.

## Contents

- `importers/mastodon/follow-hashtags/` — bulk-follow Mastodon hashtags from a file, another account's followed_tags, and/or trending tags. TypeScript, dry-run by default.
- `sites/opencode/config-generator/` — interactive wizard that generates a project or global opencode.json: model picker fed by `opencode models`, agent editor, validation via `opencode debug config`, backup before replace. Python.
- `dotfiles/` — the shell dotfiles and installer (merged from the `dotfiles` repo). See `dotfiles/README.md`; run `bash dotfiles/setup.sh` from the repo to install.

Repo: https://github.com/tonyarcher/ops-scripts
