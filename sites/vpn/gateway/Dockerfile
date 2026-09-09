# syntax=docker/dockerfile:1.7
# nginx gateway on the WireGuard address (HTTP + TCP stream forwards).
#
# What: binds WG_LISTEN_ADDR only — not the public NIC.
# Base: ubuntu:24.04
# Run:  docker compose up --build   or   ./deploy.sh up
#
# Drop extra server blocks in gateway/http.d or gateway/stream.d and rebuild.
# Do not publish :80/:443 on the host.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    WG_LISTEN_ADDR=10.13.13.1 \
    WG_HTTP_PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gettext-base \
    iproute2 \
    nginx \
    libnginx-mod-stream \
    && rm -rf /var/lib/apt/lists/* \
    && test -f /usr/lib/nginx/modules/ngx_stream_module.so

COPY gateway/nginx.conf /etc/nginx/nginx.conf
COPY gateway/templates/ /etc/nginx/templates/
COPY gateway/stream.d/ /etc/nginx/stream.d/
COPY gateway/http.d/ /etc/nginx/http.extra/
COPY gateway/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh \
    && mkdir -p /etc/nginx/http.d /run \
    && printf '%s\n' '# runtime healthz' > /etc/nginx/http.d/00-stub.conf \
    && nginx -t

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS --max-time 3 "http://${WG_LISTEN_ADDR}:${WG_HTTP_PORT}/healthz" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
