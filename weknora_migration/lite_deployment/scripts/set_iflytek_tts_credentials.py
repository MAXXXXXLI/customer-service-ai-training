#!/usr/bin/env python3
"""Store iFlytek TTS credentials without echoing or placing them in argv."""

from __future__ import annotations

import getpass
import os
import pathlib
import stat
import tempfile


ENV_FILE = pathlib.Path("/etc/training-kb/training.env")


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"error: {message}")


def _read_values(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if "=" in line and not line.startswith("#"):
            key, value = line.rstrip("\n").split("=", 1)
            values[key] = value
    return values


def main() -> int:
    if os.geteuid() != 0:
        fail("run with sudo")
    info = ENV_FILE.lstat()
    if not stat.S_ISREG(info.st_mode) or ENV_FILE.is_symlink():
        fail("training.env must be a regular non-symlink file")
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != 0 or info.st_gid != 0:
        fail("training.env must be root:root mode 0600")

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    values = _read_values(lines)
    names = (
        "IFLYTEK_TTS_APP_ID",
        "IFLYTEK_TTS_API_KEY",
        "IFLYTEK_TTS_API_SECRET",
        "IFLYTEK_TTS_API_PASSWORD",
    )
    positions = {name: [i for i, line in enumerate(lines) if line.startswith(name + "=")] for name in names}
    if any(len(found) != 1 for found in positions.values()):
        fail("training.env must contain exactly one entry for each IFLYTEK_TTS_* credential")

    app_id = input(f"讯飞 APPID [{values.get('IFLYTEK_TTS_APP_ID', '')}]: ").strip()
    if not app_id:
        app_id = values.get("IFLYTEK_TTS_APP_ID", "").strip()
    password = getpass.getpass("讯飞 APIPassword (回车保留当前/留空使用 APIKey+APISecret): ").strip()
    api_key = getpass.getpass("讯飞 APIKey (回车保留当前): ").strip()
    api_secret = getpass.getpass("讯飞 APISecret (回车保留当前): ").strip()
    if not password:
        password = values.get("IFLYTEK_TTS_API_PASSWORD", "").strip()
    if not api_key:
        api_key = values.get("IFLYTEK_TTS_API_KEY", "").strip()
    if not api_secret:
        api_secret = values.get("IFLYTEK_TTS_API_SECRET", "").strip()

    if not app_id or any(c.isspace() for c in app_id) or len(app_id) > 128:
        fail("APPID is invalid")
    if not password and not (api_key and api_secret):
        fail("provide APIPassword or both APIKey and APISecret")
    if any(c.isspace() for c in password + api_key + api_secret):
        fail("credentials must not contain whitespace")

    replacement = {
        "IFLYTEK_TTS_APP_ID": app_id,
        "IFLYTEK_TTS_API_KEY": api_key,
        "IFLYTEK_TTS_API_SECRET": api_secret,
        "IFLYTEK_TTS_API_PASSWORD": password,
    }
    for name, index in positions.items():
        lines[index[0]] = f"{name}={replacement[name]}\n"

    descriptor, temporary_name = tempfile.mkstemp(prefix=".training.env.", dir=str(ENV_FILE.parent), text=True)
    temporary = pathlib.Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, ENV_FILE)
        directory_fd = os.open(ENV_FILE.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()

    print("iFlytek TTS credentials saved securely; values were not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
