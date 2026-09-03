#!/usr/bin/env python3
"""Disable junk on a Skyworth/Amlogic Android TV over ADB.

Never uninstalls (`pm disable-user --user 0` only). Refuses protected packages
and will not disable Google home unless FLauncher is already HOME. Dry-run
unless --yes. At most 10 packages per apply.

Run:  python sites/android-tv/debloat.py list
      python sites/android-tv/debloat.py apply --batch factory-leftovers
      python sites/android-tv/debloat.py apply --batch factory-leftovers --yes

Needs adb on PATH. Host: --host or ANDROID_TV_HOST (default 10.0.0.75).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGES_PATH = HERE / "packages.json"
MAX_BATCH = 10
DEFAULT_HOST = os.environ.get("ANDROID_TV_HOST", "10.0.0.75")
DEFAULT_PORT = int(os.environ.get("ANDROID_TV_PORT", "5555"))


def load_catalog(path: Path = PACKAGES_PATH) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def protected_ids(catalog: dict) -> set[str]:
    ids = {row["id"] for row in catalog["protected"]}
    ids.add(catalog["launcher"]["google"])
    return ids


def is_protected(package: str, catalog: dict) -> bool:
    if package in protected_ids(catalog):
        return True
    lowered = package.lower()
    for fragment in catalog.get("protected_substrings", []):
        if fragment.lower() in lowered:
            return True
    return False


def batch_by_id(catalog: dict, batch_id: str) -> dict:
    for batch in catalog["batches"]:
        if batch["id"] == batch_id:
            return batch
    known = ", ".join(b["id"] for b in catalog["batches"])
    raise SystemExit(f"unknown batch {batch_id!r}. known: {known}")


def find_adb() -> str:
    found = shutil.which("adb")
    if found:
        return found
    raise SystemExit("adb not found on PATH. Install Google platform-tools.")


def run_adb(adb: str, serial: str, args: list[str], timeout: int = 60) -> str:
    cmd = [adb, "-s", serial, *args]
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise SystemExit(f"adb failed ({proc.returncode}): {' '.join(cmd)}\n{err}")
    return proc.stdout


def connect(adb: str, host: str, port: int) -> str:
    serial = f"{host}:{port}"
    proc = subprocess.run(
        [adb, "connect", serial],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if "failed to authenticate" in out.lower() or "unauthorized" in out.lower():
        raise SystemExit(
            f"TV at {serial} is unauthorized. Accept the debugging prompt on the TV, then retry."
        )
    if proc.returncode != 0 and "connected" not in out.lower():
        raise SystemExit(f"adb connect failed: {out.strip()}")
    return serial


def shell(adb: str, serial: str, command: str, timeout: int = 60) -> str:
    return run_adb(adb, serial, ["shell", command], timeout=timeout)


def parse_packages(listing: str) -> set[str]:
    names: set[str] = set()
    for line in listing.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            names.add(line.split(":", 1)[1].strip())
    return names


def home_package(adb: str, serial: str) -> str:
    out = shell(
        adb,
        serial,
        "cmd package resolve-activity -a android.intent.action.MAIN "
        "-c android.intent.category.HOME --brief",
    )
    for line in reversed(out.splitlines()):
        line = line.strip()
        if "/" in line and not line.startswith("priority"):
            return line.split("/", 1)[0]
    return ""


def apply_batch(
    catalog: dict,
    batch: dict,
    *,
    allow_launcher: bool = False,
) -> list[dict]:
    if len(batch["packages"]) > MAX_BATCH:
        raise SystemExit(
            f"batch {batch['id']} has {len(batch['packages'])} packages; max is {MAX_BATCH}"
        )
    launcher = catalog["launcher"]["google"]
    chosen: list[dict] = []
    for row in batch["packages"]:
        pkg = row["id"]
        if pkg == launcher and not allow_launcher:
            raise SystemExit(
                f"refusing to disable home {pkg}. Install FLauncher, set it as HOME, "
                "then pass --i-installed-flauncher."
            )
        if is_protected(pkg, catalog) and pkg != launcher:
            raise SystemExit(f"refusing protected package {pkg} ({row.get('why', '')})")
        chosen.append(row)
    return chosen


def cmd_list(catalog: dict) -> None:
    print(f"device: {catalog['device']['name']}")
    print("protected:")
    for row in catalog["protected"]:
        print(f"  {row['id']:48}  {row['why']}")
    print("batches:")
    for batch in catalog["batches"]:
        print(f"  {batch['id']}  ({len(batch['packages'])})  {batch['title']}")
        for row in batch["packages"]:
            print(f"    {row['id']:46}  {row['why']}")


def cmd_measure(adb: str, serial: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "meminfo.txt").write_text(
        shell(adb, serial, "dumpsys meminfo", timeout=90), encoding="utf-8"
    )
    (out_dir / "packages-all.txt").write_text(
        shell(adb, serial, "pm list packages"), encoding="utf-8"
    )
    (out_dir / "packages-disabled.txt").write_text(
        shell(adb, serial, "pm list packages -d"), encoding="utf-8"
    )
    print(f"wrote {out_dir}")
    print(f"home={home_package(adb, serial) or '(unknown)'}")


def cmd_apply(
    adb: str,
    serial: str,
    catalog: dict,
    batch: dict,
    *,
    yes: bool,
    allow_launcher: bool,
) -> None:
    rows = apply_batch(catalog, batch, allow_launcher=allow_launcher)
    if any(r["id"] == catalog["launcher"]["google"] for r in rows):
        home = home_package(adb, serial)
        replacement = catalog["launcher"]["replacement"]
        if home != replacement:
            raise SystemExit(
                f"HOME is {home or '(unknown)'}, not {replacement}. "
                "Open FLauncher, set it as home, then retry."
            )
    disabled = parse_packages(shell(adb, serial, "pm list packages -d"))
    print(f"{'APPLY' if yes else 'DRY-RUN'} batch {batch['id']}")
    for row in rows:
        pkg = row["id"]
        if pkg in disabled:
            print(f"  already-disabled  {pkg}")
            continue
        print(f"  pm disable-user --user 0 {pkg}  # {row['why']}")
        if yes:
            print("   ", shell(adb, serial, f"pm disable-user --user 0 {pkg}").strip())
            time.sleep(0.2)
    if not yes:
        print("no changes. pass --yes to disable.")


def cmd_undo(
    adb: str,
    serial: str,
    batch: dict,
    *,
    yes: bool,
) -> None:
    print(f"{'UNDO' if yes else 'DRY-RUN'} batch {batch['id']}")
    for row in batch["packages"]:
        pkg = row["id"]
        print(f"  pm enable {pkg}")
        if yes:
            print("   ", shell(adb, serial, f"pm enable {pkg}").strip())
            time.sleep(0.2)
    if not yes:
        print("no changes. pass --yes to enable.")


def cmd_undo_all(adb: str, serial: str, catalog: dict, *, yes: bool) -> None:
    print(f"{'UNDO-ALL' if yes else 'DRY-RUN'}")
    for batch in catalog["batches"]:
        for row in batch["packages"]:
            pkg = row["id"]
            print(f"  pm enable {pkg}")
            if yes:
                print("   ", shell(adb, serial, f"pm enable {pkg}").strip())
                time.sleep(0.2)
    launcher = catalog["launcher"]["google"]
    print(f"  pm enable {launcher}")
    if yes:
        print("   ", shell(adb, serial, f"pm enable {launcher}").strip())
    if not yes:
        print("no changes. pass --yes to enable.")


def cmd_disable_launcher(
    adb: str, serial: str, catalog: dict, *, yes: bool, allow_launcher: bool
) -> None:
    if not allow_launcher:
        raise SystemExit("refusing: pass --i-installed-flauncher after FLauncher is HOME.")
    replacement = catalog["launcher"]["replacement"]
    home = home_package(adb, serial)
    if home != replacement:
        raise SystemExit(f"HOME is {home or '(unknown)'}, not {replacement}.")
    pkg = catalog["launcher"]["google"]
    print(f"{'APPLY' if yes else 'DRY-RUN'} disable {pkg}")
    if yes:
        print(shell(adb, serial, f"pm disable-user --user 0 {pkg}").strip())
        time.sleep(1)
        home_after = home_package(adb, serial)
        print(f"home now {home_after}")
        if home_after != replacement:
            print("HOME is not FLauncher; re-enabling Google launcher")
            print(shell(adb, serial, f"pm enable {pkg}").strip())
            raise SystemExit("aborted: FLauncher did not take HOME")
    else:
        print("no changes. pass --yes to disable.")


def cmd_animations(adb: str, serial: str, scale: str, *, yes: bool) -> None:
    keys = (
        "window_animation_scale",
        "transition_animation_scale",
        "animator_duration_scale",
    )
    print(f"{'APPLY' if yes else 'DRY-RUN'} animation scale {scale}")
    for key in keys:
        print(f"  settings put global {key} {scale}")
        if yes:
            shell(adb, serial, f"settings put global {key} {scale}")
    if not yes:
        print("no changes. pass --yes to write.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument(
        "--yes",
        action="store_true",
        help="actually run pm disable-user / enable / settings (default is dry-run)",
    )
    p.add_argument(
        "--i-installed-flauncher",
        action="store_true",
        help="allow disabling the Google home package after FLauncher is HOME",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="print protected packages and batches")
    sub.add_parser("measure", help="dumpsys meminfo + package lists to tmp/")
    ap = sub.add_parser("apply", help="disable one batch (max 10, dry-run default)")
    ap.add_argument("--batch", required=True)
    un = sub.add_parser("undo", help="re-enable one batch")
    un.add_argument("--batch", required=True)
    sub.add_parser("undo-all", help="re-enable every catalog batch plus Google launcher")
    sub.add_parser("disable-launcher", help="disable Google home after FLauncher is HOME")
    an = sub.add_parser("animations", help="set window/transition/animator scales")
    an.add_argument("--scale", default="0.5")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    catalog = load_catalog()
    if args.cmd == "list":
        cmd_list(catalog)
        return

    adb = find_adb()
    serial = connect(adb, args.host, args.port)

    if args.cmd == "measure":
        cmd_measure(adb, serial, HERE / "tmp" / "measure")
        return
    if args.cmd == "apply":
        cmd_apply(
            adb,
            serial,
            catalog,
            batch_by_id(catalog, args.batch),
            yes=args.yes,
            allow_launcher=args.i_installed_flauncher,
        )
        return
    if args.cmd == "undo":
        cmd_undo(adb, serial, batch_by_id(catalog, args.batch), yes=args.yes)
        return
    if args.cmd == "undo-all":
        cmd_undo_all(adb, serial, catalog, yes=args.yes)
        return
    if args.cmd == "disable-launcher":
        cmd_disable_launcher(
            adb,
            serial,
            catalog,
            yes=args.yes,
            allow_launcher=args.i_installed_flauncher,
        )
        return
    if args.cmd == "animations":
        cmd_animations(adb, serial, args.scale, yes=args.yes)
        return
    raise SystemExit(f"unhandled command {args.cmd}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"adb timed out: {exc}") from exc
