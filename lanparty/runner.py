"""Runs external commands. Tests replace it with a fake that records the commands."""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Callable

# How often `on_wait` is called while a command runs
WAIT_INTERVAL_SECONDS = 5


class CommandError(Exception):
    pass


class Runner:
    def run(self, args: list[str], *, capture: bool = False, check: bool = True,
            timeout: float | None = None,
            on_wait: Callable[[float], None] | None = None) -> subprocess.CompletedProcess:
        """Runs a command. Without capture its output goes straight to the terminal (e.g. download progress).
        After `timeout` seconds the command is stopped and CommandError is raised.
        `on_wait(seconds so far)` is called every few seconds while the command runs, for commands that print
        nothing themselves (silent installers). It can't be combined with capture."""
        try:
            if on_wait is None:
                result = subprocess.run(args, text=True, capture_output=capture, timeout=timeout)
            else:
                assert not capture, "on_wait can't be combined with capture"
                result = self._wait(args, timeout, on_wait)
        except FileNotFoundError:
            raise CommandError(f"Command not found: {args[0]}") from None
        except subprocess.TimeoutExpired:
            raise CommandError(f"'{args[0]}' did not finish within {timeout / 60:g} minutes and was stopped") from None
        if check and result.returncode != 0:
            message = f"'{' '.join(args)}' exited with code {result.returncode}"
            if capture and result.stderr.strip():
                message += f": {result.stderr.strip().splitlines()[-1]}"
            raise CommandError(message)
        return result

    def _wait(self, args: list[str], timeout: float | None,
              on_wait: Callable[[float], None]) -> subprocess.CompletedProcess:
        process = subprocess.Popen(args, text=True)
        started = time.monotonic()
        while True:
            try:
                returncode = process.wait(timeout=WAIT_INTERVAL_SECONDS)
                return subprocess.CompletedProcess(args, returncode, None, None)
            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - started
                if timeout is not None and elapsed >= timeout:
                    process.kill()
                    process.wait()
                    raise
                on_wait(elapsed)

    def exists(self, command: str) -> bool:
        return shutil.which(command) is not None
