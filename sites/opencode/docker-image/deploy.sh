#!/usr/bin/env bash
# deploy.sh — build + run the opencode Docker image (Linux/macOS/WSL)
#
# What: wraps `docker compose` with env checks and friendly errors.
# Run:  ./deploy.sh              # build if needed, start detached
#       ./deploy.sh build        # build only
#       ./deploy.sh up           # start detached
#       ./deploy.sh down         # stop + remove containers
#       ./deploy.sh logs -f      # follow logs
#       ./deploy.sh shell        # exec bash as dev user
#       ./deploy.sh clean        # down + remove image + volume
#       ./deploy.sh --with-java  # build with JDK/Maven/Gradle
#
# Env:  reads .env next to this script; creates from .env.example if missing.
#       Provider keys (XAI_API_KEY, etc.) must be set in .env — never baked.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"

usage() {
  sed -n '2,15p' "$0" | sed 's/^# //;s/^#//'
}

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: '$1' not found. Install Docker Desktop / docker engine." >&2
    exit 1
  fi
}

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$ENV_EXAMPLE" ]]; then
      cp "$ENV_EXAMPLE" "$ENV_FILE"
      echo "Created $ENV_FILE from .env.example — edit provider keys before running."
      echo "  nano $ENV_FILE"
    else
      echo "error: no $ENV_FILE and no .env.example found — cannot start." >&2
      exit 1
    fi
  fi
  # nudge if keys are still blank
  if [[ -f "$ENV_FILE" ]] && ! grep -qE 'API_KEY=.+|GITHUB_TOKEN=.+' "$ENV_FILE" 2>/dev/null; then
    echo "note: $ENV_FILE has no API keys set. opencode will run but models will fail."
    echo "      Fill XAI_API_KEY / OPENCODE_GO_API_KEY etc. in $ENV_FILE"
  fi
}

compose() {
  # Use explicit --env-file only if the file exists; otherwise rely on
  # docker-compose.yml's env_file (required:false) so `docker compose config`
  # works before first deploy.
  if [[ -f "$ENV_FILE" ]]; then
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
  else
    docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

WITH_JAVA_FLAG=""
CMD="up"
EXTRA_ARGS=()

for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --with-java) WITH_JAVA_FLAG="true" ;;
    build|up|down|restart|logs|shell|clean|config|ps) CMD="$arg" ;;
    *) EXTRA_ARGS+=("$arg") ;;
  esac
done

need docker
if ! docker compose version >/dev/null 2>&1; then
  echo "error: 'docker compose' (v2) not found. Update Docker." >&2
  exit 1
fi

ensure_env

# allow --with-java to override .env for this build
if [[ "$WITH_JAVA_FLAG" == "true" ]]; then
  export WITH_JAVA=true
  echo "Building with Java (WITH_JAVA=true)"
fi

case "$CMD" in
  build)
    echo "==> building ops-opencode..."
    # shellcheck disable=SC2128  # safe expansion for bash 3.2 + set -u (macOS)
    compose build ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
    ;;
  up)
    echo "==> starting ops-opencode (detached)..."
    compose up --build -d ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
    echo "==> ok. Try:"
    echo "    docker compose -f $COMPOSE_FILE exec opencode bash"
    echo "    docker compose -f $COMPOSE_FILE logs -f"
    compose ps
    ;;
  down)
    compose down ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
    ;;
  restart)
    compose restart ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
    ;;
  logs)
    if [[ ${#EXTRA_ARGS[@]} -eq 0 ]]; then
      compose logs -f
    else
      compose logs ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
    fi
    ;;
  shell)
    compose exec opencode bash ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
    ;;
  clean)
    echo "==> stopping and removing image + volume..."
    compose down -v --rmi local ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} || true
    docker volume rm ops-opencode-data 2>/dev/null || true
    ;;
  config)
    compose config ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
    ;;
  ps)
    compose ps ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
    ;;
  *)
    echo "unknown command: $CMD" >&2
    usage; exit 1
    ;;
esac
