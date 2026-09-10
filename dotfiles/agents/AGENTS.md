# AGENTS.md (user-wide)

Global defaults for coding agents on this machine. A **project** `AGENTS.md`
overrides this file. Keep this document a language router and a lint floor —
not a copy of any one repo.

OpenCode loads `~/.config/opencode/AGENTS.md`. Setup symlinks that path to
this canonical file (`%APPDATA%\agents\AGENTS.md` on Windows,
`~/.config/agents/AGENTS.md` on Linux).

## How to write to me

This section is **personal**. Do not copy it into a project `AGENTS.md`. Project
files hold architecture, commands, and code rules only.

Write like [Google’s Developer Documentation Style Guide](https://developers.google.com/style).
Keep STE habits: short sentences, one idea, same word, imperative procedures, no hedging.

- Use short sentences. Put one idea in each sentence.
- Use the same word for the same thing. Do not switch synonyms.
- Use active voice. For procedures, use the imperative (`Do X`. `Do not Y`.).
- Do not use filler, hype, or hedging (`maybe`, `basically`, `it is worth noting`).
- Do not repeat what I already know unless I ask.
- Keep technical names as the project writes them (`rss-api`, `compose`, `X-Request-ID`).
- If you are not sure, say so in one sentence. Then ask or stop.

## Workflow

- Read the workspace `AGENTS.md` before editing that tree.
- Do not commit or push unless the user asks. Conventional commits when they do.
- Do not edit `AGENTS.md` or `opencode.json` unless the task asks.
- Verify with that repo’s own tests/lint/build. Core/data/API changes need tests.
- Dispatch `review` on the full uncommitted diff (including untracked) before
  calling the work done.

## Reuse

- Prefer a known algorithm or an existing tool over a custom one.
- Search for the usual approach first (stdlib, the workspace, the project’s stack).
- Do not invent a parser, retry/backoff, rate limiter, or protocol.
- Do not add a dependency when stdlib or the stack already does the job.

## Language pick

| Job | Language |
| --- | --- |
| Product web UI | TypeScript + Lit (see that repo’s AGENTS.md) |
| Website / HTTP API scripts | TypeScript on Bun or Node ≥23.6 |
| Agent helpers, local data, SSH glue | Python 3 + stdlib |
| Windows admin (services, PnP, audio) | PowerShell |
| POSIX wrappers / cron glue | small `sh`/`bash` — no JSON/HTML parsing |
| JVM backends / shared domain | Kotlin 2.2+ on JVM 21 (Java interop OK; new code is Kotlin) |
| Services, CLIs, concurrency, static binaries | Go |
| Memory-safe systems, no-GC hot paths, embeddable libs | Rust |
| Containers / reverse proxy | Docker Compose + nginx (Rancher Desktop on GUI; engine on Linux servers) |

Do not start Rust, Go, Kotlin, or a new JVM module “for practice.” Use them when
the job matches the table. Product repos may forbid some of these (ops-scripts
does not want Kotlin or Gradle).

## Agent tools

Helpers **you** write to get work done (analysis, fixtures, munging) are Python 3.
Prefer the stdlib. Do not add Python as an app runtime in a TypeScript repo.

- Do not reach for Node, bash, or PowerShell for a new helper unless you are
  extending an existing installer or deploy script.
- Scratch scripts stay out of git unless the user wants them kept. Kept helpers
  go in that repo’s `tools/*.py` or in ops-scripts under the right job folder.

## Shared package vs app module

Default to an app-local module. A Lit custom element is not a sharing strategy.
Extract to `packages/` only when a second consumer already exists, or when the
code is headless domain logic with a stable API — never because it “might be
reused.” Implement in the app first.

## TypeScript (web)

Strict TypeScript, no `any`, no `!` except tests. Lit for UI unless the project
says otherwise. Formatting and element prefixes live in the project file.
Untrusted URLs go through an allow-list (`http:`/`https:`). Do not log tokens.

## Python

- Type hints on every public function and method. `from __future__ import annotations`.
- Lint/format: `ruff check` and `ruff format`. Annotations: ruff `ANN`.
- Types: `mypy --strict` (or `disallow_untyped_defs` at minimum).
- Complexity: McCabe / ruff `C901` **≤ 15**. Functions **≤ ~30** lines. Split
  rather than suppress.
- Stdlib first (`pathlib`, `json`, `csv`, `subprocess`, `argparse`). `uv` for
  tools and any real dependency. No `shell=True` with interpolated strings.
- Header comment: what it does, how to run it, required env, anything destructive.

## Kotlin / Java (JVM)

From the baseball Detekt floor — do not suppress; break the function up.

- Kotlin 2.2+, JVM 21. New code is Kotlin; Java is interop and existing files.
- Domain is pure Kotlin: no Spring/`@Entity`/`jakarta.validation` in shared domain.
- Immutable `val` data classes. No `java.util.Optional`.
- Detekt: LongMethod **30**, TooManyFunctions **10** per file/class, cyclomatic
  **15**, nested depth **4**, line length **120**.
- Slice tests for HTTP and persistence; high coverage on domain logic.
- UI is web components, not server-side HTML DSLs.

## Go

Install the toolchain (`go version` on PATH). Use Go when Python/TS would be the
wrong runtime (perf, concurrency, a single static binary) — not for scraping or
one-off CSV.

- `gofmt` (or `go fmt ./...`) and `go test ./...`. `golangci-lint` when a module
  exists.
- Layout: `cmd/` for binaries, `internal/` for private packages. Modules, not GOPATH.
- No framework by default. Context on every blocking call. Do not ignore errors.
- Aim for cyclomatic complexity around the same **15** ceiling.

## Rust

Install via `rustup`. Use Rust when you need no GC, tight memory control, or a
library that must be safe to embed — not as a default CLI language (that is Go).

- `rustfmt` + `clippy` (`cargo fmt`, `cargo clippy --all-targets -- -D warnings`)
  and `cargo test`.
- No `unwrap()`/`expect()` in library code except tests or a documented crash.
- Own errors with `thiserror`/`anyhow` at the binary edge, not both everywhere.
- Keep functions small; clippy complexity lints stay on. Prefer std, then crates
  with a real need (don’t add tokio because a script sleeps once).
- `unsafe` requires a comment on the invariant. Edition 2024 (or the crate’s
  current edition); don’t mix without a reason.

## Logging

No log warehouse required yet. **Stdout is the API** so Docker, Alloy, Loki, or
VictoriaLogs can attach later without app changes. Do not add a logging SaaS
or ship a sidecar until a project asks.

**Daemons / HTTP APIs** (Node, Java, Go, Python services): one JSON object per
line on stdout/stderr. Prefer OpenTelemetry-shaped names so traces glue on later.

```json
{"ts":"2026-09-09T17:00:00.000Z","level":"info","msg":"listening","service":"rss-api","port":3001}
```

| Field | When |
| --- | --- |
| `ts` | Always. UTC RFC3339 with milliseconds. |
| `level` | Always. `debug` \| `info` \| `warn` \| `error`. Process death: `error` then exit. |
| `msg` | Always. Short stable phrase, not an interpolated novel. |
| `service` | Always. Compose service / binary name (`fitness-api`, `radio-api`). |
| `request_id` | HTTP or any unit of work. Honor `X-Request-ID` or W3C `traceparent`; otherwise generate. Echo `X-Request-ID` on the response. |
| `trace_id` / `span_id` | When a `traceparent` is present or you create a span. Hex, no dashes. |
| `session_id` | When there is an authenticated session. Opaque id, **not** the cookie or token. |
| `method` `path` `status` `duration_ms` | HTTP request summary (one line per request). |
| `err` | On failure: `{ "type", "message" }`. Stack only at `debug` or for 5xx. |
| extra keys | Event-specific (`port`, `feed_id`, …). Keep them scalar. |

`LOG_LEVEL` env (default `info` in deploy, `debug` ok in dev). Drop records below the threshold. Do not use `console.log` for daemons once JSON logging exists.

**Do not log:** tokens, cookies, passwords, `.env`, Authorization headers, raw request bodies, health-sample payloads, or query strings that carry secrets.

**CLIs / one-shot scripts:** human text on stdout is fine; `error:` on stderr. JSON only if the process is long-running.

**Language:**

- TypeScript Node: a 20-line `log({level, msg, ...})` helper writing `JSON.stringify` + `\n`. No pino/winston unless the repo already has one.
- Browser / Lit: `console` at the right level. Do not JSON-spam the user’s console; do not send client logs to a collector unless the project asks.
- Python: `logging` with a JSON formatter for daemons; plain `print`/`logging` for CLIs.
- Go: `log/slog` JSON handler. Put `request_id` on the context, not a global.
- Java/Kotlin: SLF4J + JSON encoder (Logback/Log4j2). MDC: `request_id`, `trace_id`. No `System.out`.
- nginx: keep access/error logs; don’t duplicate app request lines there.

Correlation is **request/session/trace ids**, not OS thread ids (Node/Go don’t have a useful thread). Java may add `thread` in MDC if it helps; it is not a substitute for `request_id`.

## SQL

Postgres or SQLite, parameterized queries only. Migrations are versioned files,
not ad-hoc `ALTER` in a shell. Do not concatenate user input into SQL.

## Docker / Compose

Runtime by machine:

- **Windows** and **Linux GUI**: Rancher Desktop for *local* engine work. Talk to
  it with `docker` / `docker compose` (dockerd/Moby compatibility enabled). Do
  not install or assume Docker Desktop.
- **Linux server** (no GUI): Docker Engine + the compose plugin. This is also
  the **remote** daemon GUI machines deploy to. No Rancher Desktop there, no
  Kubernetes unless the repo already has manifests.

Remote vs local: use the **repo deploy script** (`deploy.sh` / `deploy.ps1`).
Those auto-select, in order: an already-set `DOCKER_HOST`, an SSH tunnel to the
remote `docker.sock` (typically `tcp://127.0.0.1:2375` from
`ssh -N -L 2375:/var/run/docker.sock user@host`), then local Rancher. Honor
`--local` / `--remote` / `DEPLOY_TARGET` / `DOCKER_HOST` when the project
defines them. Do not `docker context` shuffle or publish the remote sock on the
LAN. The tunnel is plaintext on localhost; the SSH hop is the trust boundary.

Do not invent Swarm, k3s, or Helm unless the repo already has them. If local
`docker` fails on a GUI box, start Rancher Desktop — do not rewrite the stack to
podman. If a remote deploy fails, check the tunnel first, not the Dockerfiles.

- Prefer the repo’s deploy script (`deploy.sh`, `deploy.ps1`, or the compose
  file) over ad-hoc `docker run` / `docker build`.
- Compose `context` stays at the **repo root** unless that project’s deploy docs
  say otherwise. Do not move `deploy/` in a workbench-style repo.
- One concern per container. App images listen internally (often `3000`); a
  gateway publishes `80`/`443`. Static SPAs: nginx. APIs: the language runtime.
  Do not put Postgres in the same container as the app.
- Bake `APP_BASE_PATH` (and other public prefixes) at **image build**. Do not
  hand-edit `dist/` inside a container or on the host to “fix” paths.
- `.dockerignore` drops `node_modules`, `.git`, secrets, and local DBs. Never
  `COPY` `.env`, keys, or host `node_modules` into an image.
- Pin base image tags for deploy (not floating `:latest` on production).
  Logs to stdout/stderr. Healthcheck the published protocol.
- Windows-generated lockfiles may omit Linux optional deps — Linux image builds
  must install Linux natives in the image (`npm ci` in the Dockerfile), not copy
  them from the host.
- **Never push images to a registry** (Docker Hub, GHCR, ECR, or otherwise).
  We do not like registries. Build from the git tree on the engine that will
  run the containers (local Rancher or the remote daemon via the tunnel) and
  `compose up`. Do not `docker push`, do not tag for a registry, do not add
  `image: org/name` that implies a pull. Compose `build:` from the repo.
- Agents do not change live servers or open extra published ports unless the
  user asks.

## Secrets and environment

Project `AGENTS.md` may name extra files; it does not relax this section.

**Never commit or push** `.env`, `.env.*` (except a committed `.env.example`),
private keys, cookies, tokens, or production dumps. Do not `git add -f` them.
Before any commit, `git status` / the staged list must not contain those files.
If one is already tracked, stop and tell the user — do not `git rm --cached`
or rewrite history unless they ask.

**Where values live**

| Kind | Where |
| --- | --- |
| Placeholders (committed) | `.env.example` next to the consumer, or `config/examples/.env.example` |
| Secrets for a repo | Untracked `.env` beside the thing that reads it (`deploy/.env`, `app/.env`) |
| Secrets for a one-off | Process environment (`export` / `$env:`). Do not paste into tracked files |
| Toolchain (PATH, `JAVA_HOME`, `GOPATH`) | Shell profile (`~/.bash_env`, PowerShell profile) — **not** API tokens |
| Docker | `env_file:` / `environment:` at **run** from an untracked `.env`. Never `ARG`/`ENV` a secret at **build**, never `COPY .env` into an image |

Do not log or print secrets (including compose config dumps and debug flags).
Do not put tokens in `AGENTS.md`, Dockerfiles, or committed YAML. Empty or
obviously fake values only in examples (`replace_me`, blank).

Default destructive remote scripts to dry-run.
