# vpn

WireGuard on a provider-agnostic Linux instance (Docker Compose), plus an
nginx gateway for HTTP reverse-proxy and TCP port-forwards on the tunnel IP.
SSH to the box over `10.13.13.1` after the client is up. Not OpenVPN — one
`.conf` imports on Windows, Linux, macOS, iPad, and Android with the official
WireGuard app. iPad and Android are first-class: they exist to open the web
apps on the tunnel, not to SSH.

```
sites/vpn/
  docker-compose.yml   # wireguard + gateway, host network
  vpnconfig.py         # conf render, NAT, SSH lock (dry-run)
  deploy.py            # compose + SSH docker tunnel (Windows + Linux)
  deploy.sh            # execs deploy.py
  wireguard/           # server image
  gateway/             # nginx image (stream + http)
  clients/connect.sh   # Linux/macOS wg-quick
  clients/show-qr.py   # QR for iPad/Android WireGuard import
  mfa/                 # optional TOTP + passkey portal (WG_MFA=true)
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
| iPad | [WireGuard for iOS](https://apps.apple.com/app/wireguard/id1441195209) | QR (`show-qr.py`) or Create from file |
| Android | [WireGuard for Android](https://play.google.com/store/apps/details?id=com.wireguard.android) | QR (`show-qr.py`) or Create from file |

Append peer names; do not reorder. Order assigns `10.13.13.2`, `.3`, …:

```bash
# sites/vpn/.env  — example: WG_PEERS=laptop,ipad,android
python sites/vpn/deploy.py --remote up
python sites/vpn/deploy.py peer ipad > ipad.conf
python sites/vpn/clients/show-qr.py ipad.conf
```

`show-qr.py` needs `qrencode` on PATH. Without it, AirDrop/email `ipad.conf`
into the Files app and use **Create from file**. The conf contains a private
key; do not commit it or paste it into chat.

Split tunnel is the default (`AllowedIPs = 10.13.13.0/24`): SSH, nginx, and
other hosts on that subnet. That is enough for web apps on a VPN IP. Do not
turn on `WG_FULL_TUNNEL` just to browse them. Keepalive is already 25s (phones
behind carrier NAT).

## iPad / Android web apps

Safari and Chrome must use **IPv4 URLs** on `10.13.13.0/24`. There is no DNS
in the split-tunnel conf.

1. Install WireGuard, import the peer, toggle the tunnel on.
2. Prove it: `http://10.13.13.1:8080/healthz` must return `ok`.
3. Open the app on its tunnel address, for example `http://10.13.13.1/` if
   nginx on this box proxies it, or `http://10.13.13.4/…` if the app host is
   another WireGuard peer (`sites/hosts`).

To put a compose stack that already listens on loopback onto the tunnel, copy
`gateway/http.d/webapps.example.conf` to a `*.conf`, set `proxy_pass`, rebuild
the gateway. Always `listen 10.13.13.1:…`, never `0.0.0.0`.

## Optional MFA (TOTP + passkey)

WireGuard itself has no 2FA in the handshake. This toggle gates **HTTP on the
tunnel** (web apps) after the phone or laptop is connected. SSH stays
key-only. No Google account, no IdP.

Set in `sites/vpn/.env` and redeploy:

```
WG_MFA=true
WG_MFA_HOST=vpn.ops
```

```bash
python sites/vpn/deploy.py --remote up
python sites/vpn/deploy.py mfa-enroll ipad
# scan the otpauth:// URI with Aegis, 2FAS, or Ente Auth (any TOTP app)
```

Then on the device: tunnel on → `http://10.13.13.1:8080/mfa/` → TOTP.
That unlocks the client IP for `WG_MFA_TTL_HOURS` (default 12).

Passkeys (iCloud/Face ID, Windows Hello, or a hardware key). No Google
account required; Android may offer Google Password Manager — decline it
and use TOTP or a key if you want.

1. After TOTP, open `https://vpn.ops:8443/mfa/` (DNS for `vpn.ops` is served
   on the tunnel).
2. Install `http://10.13.13.1:8080/mfa/ca.crt` as a profile/CA on the device.
3. **Register passkey**, then later **Unlock with passkey**.

Extra nginx `location /` blocks should `include /etc/nginx/mfa-protect.inc;`
(see `webapps.example.conf`). `/healthz` stays open.

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
python sites/vpn/tests/test_show_qr.py
python sites/vpn/mfa/tests/test_totp.py
python sites/vpn/mfa/tests/test_store.py
python sites/vpn/mfa/tests/test_server.py
python sites/vpn/vpnconfig.py check
docker compose -f sites/vpn/docker-compose.yml config
ruff check sites/vpn/vpnconfig.py sites/vpn/clients/show-qr.py sites/vpn/tests sites/vpn/mfa
ruff format --check sites/vpn/vpnconfig.py sites/vpn/clients/show-qr.py sites/vpn/tests sites/vpn/mfa
mypy --strict sites/vpn/vpnconfig.py sites/vpn/clients/show-qr.py sites/vpn/mfa/server.py sites/vpn/mfa/store.py sites/vpn/mfa/totp.py
```
