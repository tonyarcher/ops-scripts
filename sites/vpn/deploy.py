#!/usr/bin/env python3
"""Build and run the WireGuard VPN stack. Works on Windows and Linux.

Wraps docker compose. Opens an SSH tunnel to VPN_HOST docker.sock when remote.
lock-ssh is dry-run unless --yes.

Run:  python sites/vpn/deploy.py --remote up
      python sites/vpn/deploy.py peer laptop
      python sites/vpn/deploy.py lock-ssh
      python sites/vpn/deploy.py lock-ssh --yes

Env:  sites/vpn/.env (copied from .env.example if missing). Never commit .env.
Progress goes to stderr so `python ... peer laptop > laptop.conf` is clean.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPOSE_FILE = HERE / "docker-compose.yml"
ENV_FILE = HERE / ".env"
ENV_EXAMPLE = HERE / ".env.example"
PLACEHOLDER_HOSTS = frozenset({"", "replace_me", "203.0.113.10"})

_tunnel: subprocess.Popen[bytes] | None = None


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip("'\"")
    return out


def ensure_env() -> None:
    if ENV_FILE.is_file():
        return
    if not ENV_EXAMPLE.is_file():
        raise SystemExit(f"error: no {ENV_FILE} and no .env.example")
    shutil.copy(ENV_EXAMPLE, ENV_FILE)
    print(f"Created {ENV_FILE} from .env.example — edit VPN_HOST before up.", file=sys.stderr)


def compose_argv(env_file: Path, extra: list[str]) -> list[str]:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE)]
    if env_file.is_file():
        cmd.extend(["--env-file", str(env_file)])
    cmd.extend(extra)
    return cmd


def run_compose(extra: list[str]) -> int:
    print("==> " + " ".join(compose_argv(ENV_FILE, extra)), file=sys.stderr)
    return subprocess.call(compose_argv(ENV_FILE, extra))


def wait_tcp(host: str, port: int, tries: int = 40) -> None:
    for _ in range(tries):
        try:
            with socket.create_connection((host, port), timeout=0.4):
                return
        except OSError:
            time.sleep(0.25)
    raise SystemExit("error: docker SSH tunnel did not listen")


def stop_tunnel() -> None:
    global _tunnel
    if _tunnel is None:
        return
    _tunnel.terminate()
    try:
        _tunnel.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _tunnel.kill()
    _tunnel = None


def start_tunnel(env: dict[str, str]) -> None:
    global _tunnel
    host = env.get("VPN_HOST", "")
    user = env.get("VPN_DEPLOY_USER") or "root"
    port = env.get("VPN_DEPLOY_SSH_PORT") or "22"
    key = env.get("VPN_DEPLOY_SSH_KEY", "")
    tunnel_port = env.get("DOCKER_TUNNEL_PORT") or "2375"
    if host in PLACEHOLDER_HOSTS:
        raise SystemExit(f"error: set VPN_HOST in {ENV_FILE} for --remote")
    if shutil.which("ssh") is None:
        raise SystemExit("error: ssh not found")
    cmd = [
        "ssh",
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-p",
        port,
        "-L",
        f"127.0.0.1:{tunnel_port}:/var/run/docker.sock",
        f"{user}@{host}",
    ]
    if key:
        cmd[1:1] = ["-i", key]
    print(f"==> SSH tunnel {user}@{host} docker.sock -> 127.0.0.1:{tunnel_port}", file=sys.stderr)
    _tunnel = subprocess.Popen(cmd)
    wait_tcp("127.0.0.1", int(tunnel_port))
    os.environ["DOCKER_HOST"] = f"tcp://127.0.0.1:{tunnel_port}"


def select_engine(args: argparse.Namespace, env: dict[str, str]) -> None:
    host = os.environ.get("DOCKER_HOST", "")
    local_tunnel = host.startswith("tcp://127.0.0.1:") or host.startswith("tcp://localhost:")
    if args.remote and local_tunnel:
        print("==> --remote: using existing localhost Docker tunnel", file=sys.stderr)
        return
    if args.remote:
        start_tunnel(env)
        return
    if host and not args.local:
        print("==> using existing DOCKER_HOST", file=sys.stderr)
        return
    if not args.local and env.get("DEPLOY_TARGET") == "remote":
        start_tunnel(env)


def need_docker() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("error: docker not found")
    if subprocess.call(["docker", "compose", "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        raise SystemExit("error: docker compose v2 not found")


def cmd_up(extra: list[str]) -> int:
    print("==> starting ops-vpn (detached)...", file=sys.stderr)
    code = run_compose(["up", "--build", "-d", *extra])
    if code != 0:
        return code
    run_compose(["ps"])
    print(f"==> fetch a client profile: {sys.argv[0]} peer laptop", file=sys.stderr)
    print(f"==> lock public SSH only after VPN login works: {sys.argv[0]} lock-ssh", file=sys.stderr)
    return 0


def cmd_peer(name: str) -> int:
    return run_compose(["exec", "-T", "wireguard", "python3", "/opt/vpn/vpnconfig.py", "print-client", "--name", name])


def cmd_lock(yes: bool) -> int:
    inner = ["lock-ssh", "--yes"] if yes else ["lock-ssh"]
    return run_compose(["exec", "-T", "wireguard", "python3", "/opt/vpn/vpnconfig.py", *inner])


def cmd_check() -> int:
    env = load_dotenv(ENV_FILE)
    os.environ.update({k: v for k, v in env.items() if k not in os.environ})
    check = subprocess.call([sys.executable, str(HERE / "vpnconfig.py"), "check", "--config-dir", str(HERE / "var")])
    if check != 0:
        return check
    code = run_compose(["config"])
    if code == 0:
        print("compose file ok", file=sys.stderr)
    return code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument(
        "command",
        nargs="?",
        default="up",
        choices=["build", "up", "down", "restart", "logs", "ps", "config", "clean", "check", "peer", "lock-ssh", "shell"],
    )
    parser.add_argument("rest", nargs="*")
    return parser.parse_args(argv)


def dispatch(args: argparse.Namespace) -> int:
    extra = list(args.rest)
    if args.command == "up":
        return cmd_up(extra)
    if args.command == "build":
        return run_compose(["build", *extra])
    if args.command == "down":
        return run_compose(["down", *extra])
    if args.command == "restart":
        return run_compose(["restart", *extra])
    if args.command == "logs":
        return run_compose(["logs", "-f", *extra] if not extra else ["logs", *extra])
    if args.command == "ps":
        return run_compose(["ps", *extra])
    if args.command == "config":
        return run_compose(["config", *extra])
    if args.command == "clean":
        print("==> removing containers, local images, and ops-vpn-config (all keys)", file=sys.stderr)
        return run_compose(["down", "-v", "--rmi", "local", *extra])
    if args.command == "check":
        return cmd_check()
    if args.command == "peer":
        if not extra:
            raise SystemExit("usage: deploy.py peer <name>")
        return cmd_peer(extra[0])
    if args.command == "lock-ssh":
        return cmd_lock(args.yes)
    return run_compose(["exec", "wireguard", "bash", *extra])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    need_docker()
    ensure_env()
    env = load_dotenv(ENV_FILE)
    try:
        if args.command != "check":
            select_engine(args, env)
        return dispatch(args)
    finally:
        stop_tunnel()


if __name__ == "__main__":
    raise SystemExit(main())
