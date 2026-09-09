# vpn

WireGuard on a provider-agnostic Linux instance (Docker Compose), plus an
nginx gateway for HTTP reverse-proxy and TCP port-forwards on the tunnel IP.
SSH to the box over `10.13.13.1` after the client is up. Not OpenVPN — one
`.conf` imports on Windows, Linux, and macOS with the official WireGuard app.

```
sites/vpn/
  docker-compose.yml   # wireguard + gateway, host network
  vpnconfig.py         # conf render, NAT, SSH lock (dry-run)
  deploy.py            # compose + SSH docker tunnel (Windows + Linux)
  deploy.sh            # execs deploy.py
  wireguard/           # server image
  gateway/             # nginx image (stream + http)
  clients/connect.sh   # Linux/macOS wg-quick
windows/scripts/deploy-ops-vpn.ps1
windows/scripts/connect-ops-vpn.ps1
```

## Quick start (server)

On the Linux instance (or from your laptop with `DEPLOY_TARGET=remote`):

```bash
cp sites/vpn/.env.example sites/vpn/.env
# edit VPN_HOST, VPN_DEPLOY_USER, WG_PEERS  (never commit .env)

python sites/vpn/deploy.py check
python sites/vpn/deploy.py --remote up     # SSH tunnel to VPN_HOST docker.sock
# or, already on the box:
python sites/vpn/deploy.py --local up
```

Windows (Rancher Desktop + OpenSSH):

```powershell
Copy-Item sites\vpn\.env.example sites\vpn\.env
# edit VPN_HOST in sites\vpn\.env
powershell -NoProfile -ExecutionPolicy Bypass -File windows\scripts\deploy-ops-vpn.ps1 --remote up
powershell ... -File windows\scripts\deploy-ops-vpn.ps1 peer laptop
```

Provider firewall: allow **UDP 51820** (or `WG_LISTEN_PORT`). Do not publish
80/443. Kernel needs WireGuard (Ubuntu 22.04+ does). Host must have
`net.ipv4.ip_forward=1` (k3s/router boxes usually already do). Docker Engine +
compose v2 on the instance. `network_mode: host` is Linux-only.

First SSH still uses the public/LAN IP. After a client handshake:

```bash
ssh deploy@10.13.13.1
```

Then, and only then, lock host sshd to the tunnel subnet (dry-run default):

```bash
python sites/vpn/deploy.py lock-ssh
python sites/vpn/deploy.py lock-ssh --yes
```

`--yes` drops new TCP/22 from outside `10.13.13.0/24` (IPv4) and drops new
IPv6 SSH entirely (this tunnel is v4-only). Existing sessions stay until they
reconnect. Rules are in-memory iptables (gone on reboot unless you persist
them). Host firewalls that already ACCEPT ssh (ufw, cloud security groups)
can shadow the DROP — check `iptables -L INPUT -n` after `--yes`. Keep a
console/VNC until you have proven VPN SSH.

`python sites/vpn/deploy.py clean` deletes the `ops-vpn-config` volume and every issued
client private key.

## Client profiles

Profiles are generated on first `up` and live in the `ops-vpn-config` volume
(not in git). They contain private keys.

```bash
python sites/vpn/deploy.py peer laptop > laptop.conf
```

| OS | Client | How |
| --- | --- | --- |
| Windows | [WireGuard for Windows](https://www.wireguard.com/install/) | Import tunnel from file, or `windows/scripts/connect-ops-vpn.ps1 -Config laptop.conf` |
| Linux | `wireguard-tools` | `bash sites/vpn/clients/connect.sh laptop.conf` |
| macOS | WireGuard app or `brew install wireguard-tools` | Import in the app, or `connect.sh` if `wg-quick` is on PATH |

Split tunnel is the default (`AllowedIPs = 10.13.13.0/24`): SSH and nginx
only. To send all IPv4 (HTTP/HTTPS) out the instance, set `WG_FULL_TUNNEL=true`
and rebuild/up. That uses NAT/MASQUERADE on the WAN NIC.

## HTTP / port-forwards

nginx listens on `10.13.13.1:8080/healthz` (tunnel only). Extra HTTP servers:
`gateway/http.d/`. TCP forwards: copy `gateway/stream.d/tcp-forward.example.conf`
to a `*.conf` and rebuild. Always `listen 10.13.13.1:...`, never `0.0.0.0`.

## Deploy target

`deploy.py` (or `deploy.sh`) picks an engine in this order: existing `DOCKER_HOST`, then an SSH
tunnel to `VPN_HOST:/var/run/docker.sock` on localhost `2375` when
`DEPLOY_TARGET=remote` or `--remote`, else local. `--local` skips the tunnel.
Does not `docker context` shuffle or publish dockerd on the LAN.

`.env.example` uses documentation IPs (`203.0.113.10`). Put your host in `.env`.

## Verification

```bash
python sites/vpn/tests/test_vpnconfig.py
python sites/vpn/tests/test_deploy.py
python sites/vpn/vpnconfig.py check
docker compose -f sites/vpn/docker-compose.yml config
ruff check sites/vpn/vpnconfig.py sites/vpn/tests
ruff format --check sites/vpn/vpnconfig.py sites/vpn/tests
mypy --strict sites/vpn/vpnconfig.py
```
