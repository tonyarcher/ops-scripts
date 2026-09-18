# syntax=docker/dockerfile:1.7
# Optional MFA portal (TOTP + FIDO2). Build on the engine that will run it.
FROM python:3.12-slim-bookworm

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
COPY mfa/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY mfa/server.py mfa/store.py mfa/totp.py mfa/page.html /app/
COPY mfa/make-certs.sh /make-certs.sh
COPY mfa/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /make-certs.sh /entrypoint.sh

EXPOSE 9090
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; raise SystemExit(0 if urllib.request.urlopen('http://127.0.0.1:9090/whoami', timeout=5).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
