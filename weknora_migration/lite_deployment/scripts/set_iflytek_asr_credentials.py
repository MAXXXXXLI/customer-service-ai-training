#!/usr/bin/env python3
"""Store iFlytek streaming voice-dictation credentials without exposing them.

The application may reuse the TTS APPID/APIKey/APISecret for IAT.  This helper
is only needed when the iFlytek console issues or requires a distinct set of
voice-dictation HMAC credentials.
"""

from __future__ import annotations

import getpass
import os
import pathlib
import stat
import tempfile
from typing import NoReturn


ENV_FILE = pathlib.Path("/etc/training-kb/training.env")
NAMES = (
    "IFLYTEK_IAT_APP_ID",
    "IFLYTEK_IAT_API_KEY",
    "IFLYTEK_IAT_API_SECRET",
)


def fail(message: str) -> NoReturn:
    raise SystemExit(f"error: {message}")


def read_values(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if "=" in line and not line.startswith("#"):
            name, value = line.rstrip("\n").split("=", 1)
            values[name] = value
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
    values = read_values(lines)
    positions = {name: [index for index, line in enumerate(lines) if line.startswith(name + "=")] for name in NAMES}
    if any(len(indices) != 1 for indices in positions.values()):
        fail("training.env must contain exactly one entry for each IFLYTEK_IAT_* credential")

    print("留空并直接回车会继续复用 IFLYTEK_TTS_APP_ID/API_KEY/API_SECRET。")
    app_id = input(f"讯飞语音听写 APPID [{values.get('IFLYTEK_IAT_APP_ID', '')}]: ").strip()
    api_key = getpass.getpass("讯飞语音听写 APIKey: ").strip()
    api_secret = getpass.getpass("讯飞语音听写 APISecret: ").strip()
    if not app_id and not api_key and not api_secret:
        replacement = {name: "" for name in NAMES}
    else:
        existing = {name: values.get(name, "").strip() for name in NAMES}
        replacement = {
            "IFLYTEK_IAT_APP_ID": app_id or existing["IFLYTEK_IAT_APP_ID"],
            "IFLYTEK_IAT_API_KEY": api_key or existing["IFLYTEK_IAT_API_KEY"],
            "IFLYTEK_IAT_API_SECRET": api_secret or existing["IFLYTEK_IAT_API_SECRET"],
        }
        if not all(replacement.values()):
            fail("provide all of APPID, APIKey and APISecret, or leave all fields blank to reuse TTS HMAC credentials")
        if any(any(char.isspace() for char in value) or len(value) > 256 for value in replacement.values()):
            fail("credentials must be short values without whitespace")

    for name, indices in positions.items():
        lines[indices[0]] = f"{name}={replacement[name]}\n"

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

    print("iFlytek voice-dictation credentials saved securely; values were not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
