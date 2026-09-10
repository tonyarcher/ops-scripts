# hosts

Named machines you SSH to or run Compose on. VPN (`sites/vpn`) and Docker stay
the runtimes. This list is the inventory layer: `vpn-gw`, `gpu-1`, `cad-ws`.

Copy the example and edit. Never commit `hosts.json`.

```bash
cp sites/hosts/hosts.example.json sites/hosts/hosts.json
# replace 203.0.113.x documentation IPs with real SSH targets

python sites/hosts/inventory.py list
python sites/hosts/inventory.py show gpu-1
python sites/hosts/inventory.py ssh-cmd gpu-1
python sites/hosts/inventory.py check
```

`--file` overrides the path. Without it, `hosts.json` wins if present, else the
example (stderr notes that).

## Roles

| Role | What |
| --- | --- |
| `vpn` | WireGuard + nginx gateway |
| `gpu` | NVIDIA Linux, Docker Engine, CUDA (CAD batch / LLM) |
| `llm` | Long-running inference host (often the same box as `gpu`) |
| `cad` | Interactive CAD workstation. Host GPU. Not a container. |

A Mac laptop is a **client** (`macos/`). It has no NVIDIA CUDA. Do not put one
here as a GPU worker.

GUI CAD stays on `cad-ws`. Stream the desktop over the tunnel if the laptop is
thin. Do not run that GUI in Docker. Batch CUDA jobs belong on `gpu-1`.

Do not add Swarm, k3s, or a VM tree. A rented cloud GPU box is just another
row with `docker: true`.

## Fields

JSON, stdlib only. Required: `name`, `role`, `ssh_user`, `ssh_host`, `gpu`,
`docker`. Optional: `ssh_port` (22), `ssh_key` (path, not key material),
`vpn_ip`, `notes`.

`ssh-cmd` prints a copy-paste `ssh` line. Other scripts can grow a `--host`
flag later; this tool does not call `deploy.py`.

## Verification

```bash
python sites/hosts/tests/test_inventory.py
python sites/hosts/inventory.py --file sites/hosts/hosts.example.json check
ruff check sites/hosts/inventory.py sites/hosts/tests
ruff format --check sites/hosts/inventory.py sites/hosts/tests
mypy --strict sites/hosts/inventory.py
```
