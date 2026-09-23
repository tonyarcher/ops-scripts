# syntax=docker/dockerfile:1.7
# opencode dev image — Node now, Java later.
#
# What: reproducible opencode + Node toolchain for AI agents.
# Base: Ubuntu 24.04 (lets us apt-install JDK later without switching image).
# Run:  docker compose up --build   or   ./deploy.sh
#       docker build --build-arg WITH_JAVA=true -t ops-opencode .
#
# Build args:
#   NODE_VERSION  Node major (default 24, matches host on 2026-09-04)
#   WITH_JAVA     true|false — adds openjdk-21-jdk + maven + gradle
#   WITH_BUN      true|false — adds bun
#
# Secrets: never baked. Pass provider keys at runtime via --env-file .env
#   (XAI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENCODE_GO_API_KEY, etc.)
# Build locally (`compose up --build`). Do not docker push / use a registry.
# See README.md and .env.example.

ARG NODE_VERSION=24
ARG WITH_JAVA=false
ARG WITH_BUN=true

FROM ubuntu:24.04 AS base

ARG NODE_VERSION=24
ARG WITH_JAVA=false
ARG WITH_BUN=true

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    NODE_VERSION=${NODE_VERSION}

# --- 1. Base CLI tools agents expect ---
# Keep this layer cache-friendly. Additions here = slowest to rebuild.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget gnupg lsb-release apt-transport-https \
    git gh openssh-client \
    ripgrep fd-find fzf jq tree unzip zip tar \
    bat build-essential pkg-config \
    python3 python3-pip pipx \
    sudo locales zsh htop less nano vim \
    # docker CLI + daemon (ubuntu's docker.io). Agents only need the CLI
    # to run `docker build`; daemon is unused unless you mount /var/run/docker.sock
    docker.io \
    && rm -rf /var/lib/apt/lists/* \
    # fd is `fdfind` on Ubuntu, add symlink so `fd` works
    && if command -v fdfind >/dev/null 2>&1 && [ ! -e /usr/local/bin/fd ]; then ln -s "$(command -v fdfind)" /usr/local/bin/fd; fi \
    # bat is `batcat` on Ubuntu
    && if command -v batcat >/dev/null 2>&1 && [ ! -e /usr/local/bin/bat ]; then ln -s "$(command -v batcat)" /usr/local/bin/bat; fi \
    && locale-gen en_US.UTF-8

# --- 2. Node toolchain (nodesource) ---
# Versions float on purpose: this dev image tracks current toolchains and the
# base image tag pins the suite. Rebuild to move forward.
# hadolint ignore=DL3016
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_VERSION}.x" -o /tmp/nodesource.sh \
    && bash /tmp/nodesource.sh \
    && rm -f /tmp/nodesource.sh \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version \
    # pnpm + yarn via corepack
    && corepack enable \
    && corepack prepare pnpm@latest --activate \
    && corepack prepare yarn@stable --activate \
    && npm install -g npm@latest

# Bun (optional, fast for TS/HTTP jobs per AGENTS.md).
# BUN_INSTALL=/usr/local puts the binary on the default PATH for root and dev.
# Prepending that bin dir makes the installer skip writing shell rc files.
RUN if [ "$WITH_BUN" = "true" ]; then \
      export BUN_INSTALL=/usr/local \
      && mkdir -p "$BUN_INSTALL/bin" \
      && export PATH="$BUN_INSTALL/bin:$PATH" \
      && curl -fsSL https://bun.sh/install -o /tmp/install-bun.sh \
      && bash /tmp/install-bun.sh \
      && rm -f /tmp/install-bun.sh \
      && ln -sf bun /usr/local/bin/bunx \
      && bun --version; \
    fi

# --- 3. opencode ---
# Install globally so `opencode` is on PATH for any user.
# Version floats on purpose: this dev image tracks the current CLI and the base
# image tag pins the suite. Pin here if you need reproducible builds.
# Fail loud — do not mask npm errors with || echo fallback.
# hadolint ignore=DL3016
RUN npm install -g @opencode-ai/cli
RUN opencode --version 2>/dev/null || opencode2 --version 2>/dev/null

# --- 4. Java (opt-in, keeps default image small) ---
RUN if [ "$WITH_JAVA" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends \
        openjdk-21-jdk maven gradle \
      && rm -rf /var/lib/apt/lists/* \
      && java -version \
      && mvn -version; \
    fi

# --- 5. Non-root dev user (agents + file perms) ---
# Ubuntu 24.04 ships a default `ubuntu` user with uid/gid 1000, so naive
# groupadd/useradd -u 1000 fails. Remove any existing occupant first.
# The dev user's login name and numeric ids are build inputs, not secrets.
# hadolint ignore=DL3064
ARG USERNAME=dev
# hadolint ignore=DL3064
ARG UID=1000
# hadolint ignore=DL3064
ARG GID=1000
# No `getent | cut` pipe here: dash has no pipefail, so a failed getent would
# silently yield an empty name. Parameter expansion cannot mask a failure.
RUN if getent passwd ${UID} >/dev/null; then \
        passwd_entry=$(getent passwd ${UID}); \
        existing_user=${passwd_entry%%:*}; \
        userdel -r "$existing_user" 2>/dev/null || userdel "$existing_user" 2>/dev/null || true; \
    fi \
    && if getent group ${GID} >/dev/null; then \
        group_entry=$(getent group ${GID}); \
        existing_grp=${group_entry%%:*}; \
        groupdel "$existing_grp" 2>/dev/null || true; \
    fi \
    && groupadd -g ${GID} ${USERNAME} \
    && useradd -l -m -u ${UID} -g ${GID} -s /bin/bash ${USERNAME} \
    && mkdir -p /etc/sudoers.d \
    && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME} \
    && mkdir -p /workspace /home/${USERNAME}/.config/opencode /home/${USERNAME}/.local/share/opencode \
    && chown -R ${USERNAME}:${USERNAME} /workspace /home/${USERNAME}

# Default opencode config location — mount your real one at runtime.
# If you want to bake a default, uncomment and add opencode.json next to this Dockerfile:
# COPY --chown=dev:dev opencode.json /home/dev/.config/opencode/opencode.json

USER ${USERNAME}
WORKDIR /workspace
ENV HOME=/home/${USERNAME} \
    SHELL=/bin/bash

# Ensure bun + pipx shims on PATH for the dev user
ENV PATH="/home/${USERNAME}/.local/bin:/usr/local/bin:${PATH}"

# Useful ports for `npm run dev` / Vite / Next / etc. Expose but don't publish by default;
# compose publishes them.
EXPOSE 3000 5173 8080 8000 4096

CMD ["/bin/bash"]
