from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
from stat import S_ISDIR
import sys

import paramiko


EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache"}
EXCLUDED_FILES = {".env"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload the project to Raspberry Pi over SSH")
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", default=os.environ.get("RASPBERRY_PI_PASSWORD", ""))
    parser.add_argument("--local-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--remote-dir", default="/home/pi/rassberry-assistant")
    parser.add_argument("--run-install", action="store_true")
    parser.add_argument("--skip-service", action="store_true")
    return parser.parse_args()


def iter_files(root: Path):
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.is_file() and path.name not in EXCLUDED_FILES:
            yield path


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_path: str) -> None:
    parts = remote_path.strip("/").split("/")
    current = ""
    for part in parts:
        current += "/" + part
        try:
            st_mode = sftp.stat(current).st_mode
            if not S_ISDIR(st_mode):
                raise RuntimeError(f"{current} exists but is not a directory")
        except OSError:
            sftp.mkdir(current)


def upload_tree(sftp: paramiko.SFTPClient, local_root: Path, remote_root: str) -> None:
    ensure_remote_dir(sftp, remote_root)
    for local_path in iter_files(local_root):
        relative = local_path.relative_to(local_root).as_posix()
        remote_path = f"{remote_root}/{relative}"
        ensure_remote_dir(sftp, str(Path(remote_path).parent).replace("\\", "/"))
        sftp.put(str(local_path), remote_path)
        print(f"Uploaded {relative}")


def run_remote(client: paramiko.SSHClient, command: str) -> int:
    stdin, stdout, stderr = client.exec_command(command, timeout=3600)
    exit_status = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if out:
        sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
    if err:
        sys.stdout.buffer.write(err.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
    return exit_status


def main() -> None:
    args = parse_args()
    if not args.password:
        raise SystemExit("Password is required. Pass --password or set RASPBERRY_PI_PASSWORD.")

    local_root = Path(args.local_root).resolve()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.user, password=args.password, timeout=15)

    try:
        with client.open_sftp() as sftp:
            upload_tree(sftp, local_root, args.remote_dir)

        if args.run_install:
            install_cmd = (
                f"cd {shlex.quote(args.remote_dir)} && "
                f"echo {shlex.quote(args.password)} | sudo -S bash scripts/install_pi.sh "
                f"--app-dir {shlex.quote(args.remote_dir)} --user {shlex.quote(args.user)}"
            )
            if args.skip_service:
                install_cmd += " --skip-service"
            status = run_remote(client, install_cmd)
            if status != 0:
                raise SystemExit(status)
    finally:
        client.close()


if __name__ == "__main__":
    main()
