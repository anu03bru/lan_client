#!/usr/bin/env python3
"""Install or uninstall the LAN party games listed in games.toml.

    ./lan.py                          menu: pick a game number, then 1 = install, 2 = uninstall, 3 = back
    ./lan.py list
    ./lan.py install <game|all>
    ./lan.py uninstall <game|all> [--yes]

On Windows use `py lan.py ...`. On macOS `./lan.py` works when Python 3.11+ is installed.
"""

import sys

if sys.version_info < (3, 11):
    sys.exit("ERROR: Python 3.11 or newer is needed. "
             "Windows: winget install Python.Python.3.12. macOS: the installer from python.org")

from lanparty.cli import main  # noqa: E402  (after the version check, it needs tomllib)

if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit("\nCancelled.")
