"""Test doubles for the command runner."""

from __future__ import annotations

import io
import subprocess
from typing import Callable

from lanparty.config import parse_games
from lanparty.steps import Steps


class FakeRunner:
    """Records commands. `respond` decides the result of each command."""

    def __init__(self, commands: set[str] | None = None,
                 respond: Callable[[list[str]], tuple[int, str]] | None = None) -> None:
        self.commands = commands if commands is not None else {"flatpak", "ufw"}
        self.respond = respond or (lambda args: (0, ""))
        self.calls: list[list[str]] = []
        self.timeouts: list[float | None] = []

    def run(self, args, *, capture=False, check=True, timeout=None, on_wait=None):
        self.calls.append(list(args))
        self.timeouts.append(timeout)
        if on_wait is not None:
            # Like a command that runs for a while
            on_wait(5)
            on_wait(95)
        returncode, stdout = self.respond(list(args))
        if check and returncode != 0:
            raise RuntimeError(f"{args} failed")
        return subprocess.CompletedProcess(args, returncode, stdout, "")

    def exists(self, command):
        return command in self.commands

    def joined(self) -> list[str]:
        return [" ".join(call) for call in self.calls]


class FakeUfw:
    """A small stateful ufw: `status numbered` lists the rules, `--force delete N` removes one."""

    def __init__(self, rules: list[tuple[str, str]], active: bool = True) -> None:
        self.rules = list(rules)  # (port spec, comment)
        self.active = active

    def respond(self, args: list[str]) -> tuple[int, str] | None:
        if args[:2] != ["sudo", "ufw"]:
            return None
        command = args[2:]
        if command == ["status"]:
            return 0, "Status: active\n" if self.active else "Status: inactive\n"
        if command == ["status", "numbered"]:
            lines = ["Status: active", "", "     To                         Action      From",
                     "     --                         ------      ----"]
            for number, (port, comment) in enumerate(self.rules, start=1):
                suffix = f"                   # {comment}" if comment else ""
                lines.append(f"[{number:2}] {port:<26} ALLOW IN    Anywhere{suffix}")
            return 0, "\n".join(lines) + "\n"
        if command[:2] == ["--force", "delete"]:
            del self.rules[int(command[2]) - 1]
            return 0, "Rule deleted\n"
        if command[0] == "allow":
            # "allow 2759/udp comment X" or "allow proto udp from <net> port 2757 to any comment X"
            comment_at = command.index("comment")
            self.rules.append((" ".join(command[1:comment_at]), command[comment_at + 1]))
            return 0, "Rule added\n"
        return 0, ""


def quiet_steps() -> tuple[Steps, io.StringIO]:
    output = io.StringIO()
    return Steps(stream=output, color=False), output


def game_from_toml(text: str):
    import tomllib

    return parse_games(tomllib.loads(text))[0]
