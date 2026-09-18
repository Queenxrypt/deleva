"""Enables ``python -m deleva <command>``. See deleva/cli.py."""

from __future__ import annotations

import sys

from deleva.cli import main

if __name__ == "__main__":
    sys.exit(main())
