#!/usr/bin/env python3
"""Fail CI when line coverage of the backend *core* packages drops below the target.

Usage: coverage_gate.py coverage.xml [--min 85]

Core packages (see docs/PLAN.md, "Quality bar"): obd, storage, perf, radar.alerts,
copilot.grounding, copilot.policy.  Files that are explicitly hardware-only are omitted by
``[tool.coverage.run] omit`` in pyproject.toml and therefore never appear in the report.
Packages that do not exist yet (early PRs) are skipped so the gate is usable from PR 0.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CORE_PREFIXES = (
    "gti_copilot/obd/",
    "gti_copilot/storage/",
    "gti_copilot/perf/",
    "gti_copilot/radar/alerts.py",
    "gti_copilot/radar/hotspots.py",
    "gti_copilot/copilot/grounding.py",
    "gti_copilot/copilot/policy.py",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path)
    ap.add_argument("--min", type=float, default=85.0)
    args = ap.parse_args()

    if not args.report.exists():
        print(f"coverage report {args.report} not found", file=sys.stderr)
        return 2

    root = ET.parse(args.report).getroot()
    covered = 0
    total = 0
    per_file: list[tuple[str, int, int]] = []
    for cls in root.iter("class"):
        filename = cls.get("filename", "").replace("\\", "/")
        norm = filename.split("src/")[-1]
        if not norm.startswith(CORE_PREFIXES):
            continue
        lines = cls.find("lines")
        if lines is None:
            continue
        f_total = 0
        f_cov = 0
        for line in lines.iter("line"):
            f_total += 1
            if int(line.get("hits", "0")) > 0:
                f_cov += 1
        per_file.append((norm, f_cov, f_total))
        covered += f_cov
        total += f_total

    if total == 0:
        print("coverage gate: no core packages present yet, skipping")
        return 0

    pct = 100.0 * covered / total
    for name, c, t in sorted(per_file):
        print(f"  {name:60s} {100.0 * c / t if t else 100:6.1f}%  ({c}/{t})")
    print(f"coverage gate: core packages {pct:.1f}% (target {args.min:.0f}%)")
    return 0 if pct >= args.min else 1


if __name__ == "__main__":
    raise SystemExit(main())
