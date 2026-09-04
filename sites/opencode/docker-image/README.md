# opencode docker image

Reproducible `opencode` + Node dev container. Node now, Java later via build arg. Keeps the glitchy host `nvm`/tool drift out of the loop and gives agents the CLI tools they expect.

## Layout

```
sites/opencode/docker-image/
  Dockerfile          # Ubuntu 24.04 + Node 24 + opencode + agent CLIs; Java opt-in
  docker-compose.yml  # dev service with volumes + env_file
  .env.example        # copy to .env, fill provider keys (gitignored)
  deploy.sh           # Linux/macOS/WSL wrapper around docker compose
  README.md           # this file
windows/scripts/
  deploy-opencode-docker.ps1  # Windows wrapper (same commands)
```

## Quick start

### Linux / macOS / WSL

```bash
cp sites/opencode/docker-image/.env.example sites/opencode/docker-image/.env
nano sites/opencode/docker-image/.env   # set XAI_API_KEY, OPENCODE_GO_API_KEY, etc.

# build + run detached (creates .env from example if missing)
bash sites/opencode/docker-image/deploy.sh
# or
bash sites/opencode/docker-image/deploy.sh up

# open a shell inside
bash sites/opencode/docker-image/deploy.sh shell
docker compose -f sites/opencode/docker-image/docker-compose.yml exec opencode bash

# logs / stop
bash sites/opencode/docker-image/deploy.sh logs -f
bash sites/opencode/docker-image/deploy.sh down
```

### Windows (PowerShell)

```powershell
Copy-Item sites/opencode/docker-image/.env.example sites/opencode/docker-image/.env
notepad sites/opencode/docker-image/.env

powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/deploy-opencode-docker.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/deploy-opencode-docker.ps1 -Command shell
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/deploy-opencode-docker.ps1 -Command logs
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/deploy-opencode-docker.ps1 -Command down
```

### Raw docker compose (no wrapper)

```bash
cp sites/opencode/docker-image/.env.example sites/opencode/docker-image/.env
docker compose -f sites/opencode/docker-image/docker-compose.yml --env-file sites/opencode/docker-image/.env up --build -d
docker compose -f sites/opencode/docker-image/docker-compose.yml exec opencode bash
docker compose -f sites/opencode/docker-image/docker-compose.yml logs -f
```

## Environment variables (the only way to pass tokens)

**Never bake tokens into the image.** The image reads nothing at build time. Tokens are injected at `docker run` via `.env`.

1. Copy the template: `cp .env.example .env`
2. Fill only what you need:

| Var | Why |
|-----|-----|
| `XAI_API_KEY` | `xai/grok-4.6#max` (your `plan` agent) |
| `OPENCODE_GO_API_KEY` or `OPENCODE_API_KEY` | `opencode-go/muse-spark` / `opencode-go/glm-5.3-flash` — check `opencode auth` for exact name |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | any model routed through those providers |
| `GITHUB_TOKEN` | `gh` CLI inside container |

Leave unused vars blank. `docker-compose.yml` uses `env_file: .env` so every key in `.env` becomes an env var in the container. You can also `export XAI_API_KEY=...` before `deploy.sh` — it will be picked up.

To confirm what the container sees:

```bash
docker compose -f sites/opencode/docker-image/docker-compose.yml exec opencode env | sort | grep -E 'API_KEY|GITHUB'
```

Add new secrets to `config/examples/.env.example` as well if they apply broadly.

## Modifying the image

### Node version

In `.env` (or at build time):

```bash
NODE_VERSION=22 bash sites/opencode/docker-image/deploy.sh build
# or edit .env then
bash sites/opencode/docker-image/deploy.sh build
```

Or directly:

```bash
docker build --build-arg NODE_VERSION=22 -f sites/opencode/docker-image/Dockerfile -t ops-opencode sites/opencode/docker-image
```

### Enable Java (when you need it)

No need to rebuild the base until then. Flip the flag:

```bash
# via .env
WITH_JAVA=true bash sites/opencode/docker-image/deploy.sh build

# or one-off
bash sites/opencode/docker-image/deploy.sh --with-java build
bash sites/opencode/docker-image/deploy.sh --with-java up

# Windows
powershell -File windows/scripts/deploy-opencode-docker.ps1 -WithJava -Command build
```

This adds `openjdk-21-jdk`, `maven`, `gradle`. Disable again with `WITH_JAVA=false` and rebuild to slim back down.

### Add CLI tools

Edit `Dockerfile` `apt-get install` block. Keep it sorted. Example:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    ...existing... \
    shellcheck shfmt \
    && rm -rf /var/lib/apt/lists/*
```

Then:

```bash
bash sites/opencode/docker-image/deploy.sh build
```

### Add a baked opencode config

By default the image has no baked `opencode.json` — you mount the repo (`../../..:/workspace`) and the container reads `opencode.json` from the workspace or from `~/.config/opencode`. To bake a default:

1. Put `opencode.json` next to the `Dockerfile`.
2. Uncomment in `Dockerfile`:

   ```dockerfile
   COPY --chown=dev:dev opencode.json /home/dev/.config/opencode/opencode.json
   ```

### Change mounted workspace

`docker-compose.yml` mounts `../../..` (the `ops-scripts` repo). For another app:

```yaml
volumes:
  - /absolute/path/to/my-app:/workspace:cached
```

Or override at runtime:

```bash
docker compose -f sites/opencode/docker-image/docker-compose.yml run --volume "$PWD:/workspace:cached" opencode bash
```

### Persistent opencode state

`opencode-data` volume keeps `~/.local/share/opencode/opencode.db` across restarts. To wipe:

```bash
bash sites/opencode/docker-image/deploy.sh clean   # also removes image
docker volume rm ops-opencode-data
```

### Ports

Common dev ports are mapped (`3000`, `5173`, `8080`, `8000`, `4096`). Override in `.env`:

```
PORT_3000=3001
```

## Verification

```bash
# validate compose file without running
docker compose -f sites/opencode/docker-image/docker-compose.yml config

# check wrappers
bash sites/opencode/docker-image/deploy.sh --help
powershell -NoProfile -Command "Get-Help windows/scripts/deploy-opencode-docker.ps1 -Full"

# quick container smoke test
docker compose -f sites/opencode/docker-image/docker-compose.yml run --rm opencode bash -c "node --version; npm --version; opencode --version; rg --version; fd --version; jq --version"
```

## Troubleshooting

* `no API keys set` — you copied `.env.example` but didn't fill keys. Edit `.env`.
* `permission denied` on `deploy.sh` — `chmod +x sites/opencode/docker-image/deploy.sh`.
* `port already allocated` — change `PORT_*` in `.env` or stop the host process.
* `cannot connect to docker daemon` — start Docker Desktop / `sudo systemctl start docker`.
