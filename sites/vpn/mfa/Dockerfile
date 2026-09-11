# syntax=docker/dockerfile:1.7
# Optional MFA portal (TOTP + FIDO2). Build on the engine that will run it.
FROM node:23.11.0-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    WG_CONFIG_DIR=/config \
    MFA_BIND=127.0.0.1 \
    MFA_PORT=9090

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY mfa/package.json /app/package.json
RUN npm install --omit=dev
COPY mfa/server.ts mfa/store.ts mfa/totp.ts mfa/page.html /app/
COPY mfa/make-certs.sh /make-certs.sh
COPY mfa/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /make-certs.sh /entrypoint.sh

EXPOSE 9090
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:9090/whoami').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

ENTRYPOINT ["/entrypoint.sh"]
