"""Runs external commands. Tests replace it with a fake that records the commands."""

from __future__ import annotations

import shutil
import subprocess


class CommandError(Exception):
    pass


class Runner:
    def run(self, args: list[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
        """Runs a command. Without capture its output goes straight to the terminal (e.g. download progress)."""
        try:
            result = subprocess.run(args, text=True, capture_output=capture)
        except FileNotFoundError:
            raise CommandError(f"Command not found: {args[0]}") from None
        if check and result.returncode != 0:
            message = f"'{' '.join(args)}' exited with code {result.returncode}"
            if capture and result.stderr.strip():
                message += f": {result.stderr.strip().splitlines()[-1]}"
            raise CommandError(message)
        return result

    def exists(self, command: str) -> bool:
        return shutil.which(command) is not None
