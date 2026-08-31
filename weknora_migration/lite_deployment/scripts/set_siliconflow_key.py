#!/usr/bin/env python3
"""Store the SiliconFlow API key without echoing it or placing it in argv."""

from __future__ import annotations

import getpass
import os
import pathlib
import stat
import tempfile


ENV_FILE = pathlib.Path("/etc/training-kb/training.env")


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"error: {message}")


def main() -> int:
    if os.geteuid() != 0:
        fail("run with sudo")

    info = ENV_FILE.lstat()
    if not stat.S_ISREG(info.st_mode) or ENV_FILE.is_symlink():
        fail("training.env must be a regular non-symlink file")
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != 0 or info.st_gid != 0:
        fail("training.env must be root:root mode 0600")

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    positions = [index for index, line in enumerate(lines) if line.startswith("SILICONFLOW_API_KEY=")]
    if len(positions) != 1:
        fail("training.env must contain exactly one SILICONFLOW_API_KEY entry")

    api_key = getpass.getpass("SiliconFlow API Key (hidden): ").strip()
    if not api_key.startswith("sk-") or not 20 <= len(api_key) <= 256:
        fail("the key shape is invalid")
    if any(character.isspace() for character in api_key):
        fail("the key must not contain whitespace")

    lines[positions[0]] = f"SILICONFLOW_API_KEY={api_key}\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".training.env.", dir=str(ENV_FILE.parent), text=True
    )
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

    print("SiliconFlow key saved securely; value was not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
