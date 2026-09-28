"""Command-line entry point. Subcommands are added as the corresponding services land."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from gti_copilot import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gti-copilot",
        description="Read-only OBD-II dashboard and in-car co-pilot for a MK7 Golf GTI.",
    )
    parser.add_argument("--version", action="version", version=f"gti-copilot {__version__}")
    parser.add_subparsers(dest="command")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 1
    return 0
