"""Step runner with the same output as the old install scripts: "==> Step", then OK, WARNING or ERROR."""

from __future__ import annotations

import sys
from typing import Any, Callable, TextIO


class StepFailed(Exception):
    """A required step failed. The install of this game stops."""


class Steps:
    def __init__(self, stream: TextIO = sys.stdout, color: bool | None = None) -> None:
        self.stream = stream
        self.color = stream.isatty() if color is None else color
        self.warnings: list[str] = []

    def run(self, name: str, hint: str, action: Callable[..., Any], *args: Any) -> Any:
        """Runs a required step. On failure it prints the hint and raises StepFailed."""
        self._print(f"==> {name}")
        try:
            result = action(*args)
        except Exception as error:
            self._print(f'ERROR: "{name}" failed.', "red")
            self._print(f"Details: {error}", "red")
            self._print(f"Hint: {hint}", "red")
            raise StepFailed(name) from error
        self.ok(result)
        return result

    def attempt(self, name: str, hint: str, action: Callable[..., Any], *args: Any) -> None:
        """Runs an optional step. On failure it only warns, and the caller continues."""
        self._print(f"==> {name}")
        try:
            result = action(*args)
        except Exception as error:
            self._print(f'WARNING: "{name}" failed.', "yellow")
            self._print(f"Details: {error}", "yellow")
            self._print(f"Hint: {hint}", "yellow")
            self.warnings.append(name)
            return
        self.ok(result)

    def ok(self, result: Any = None) -> None:
        # An action can return a short note, e.g. "nothing to do"
        self._print(f"OK ({result})" if isinstance(result, str) and result else "OK", "green")

    def warn(self, message: str) -> None:
        """A warning that is not a failed step, e.g. a version mismatch."""
        self._print(f"WARNING: {message}", "yellow")

    def version_result(self, installed_version: str, expected_version: str) -> None:
        """Ends a "Check version" step. A different version only warns: the game still works for single player."""
        if installed_version and installed_version.startswith(expected_version):
            self.ok(f"version {installed_version}")
        else:
            self.warn(f'Installed version is "{installed_version}", expected "{expected_version}".')
            self.warn("Multiplayer only works reliably if all players have the same version. Tell the organizer.")
            # Listed once in the final summary, so the install doesn't end with a plain "Done!"
            self.warnings.append("Check version")

    def info(self, message: str, color: str | None = None) -> None:
        self._print(message, color)

    def _print(self, message: str, color: str | None = None) -> None:
        codes = {"red": "\033[0;31m", "yellow": "\033[0;33m", "green": "\033[0;32m", "heading": "\033[1;36m"}
        if self.color and color:
            message = f"{codes[color]}{message}\033[0m"
        print(message, file=self.stream, flush=True)
