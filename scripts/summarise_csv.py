#!/usr/bin/env python3
"""Small CSV summary helper for experiment logs."""
import argparse
import csv
from pathlib import Path
from statistics import mean


def numeric(values):
    out = []
    for value in values:
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            pass
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("csv_path")
    args = p.parse_args()

    path = Path(args.csv_path)
    rows = list(csv.DictReader(path.open()))
    print(f"{path}: {len(rows)} rows")
    if not rows:
        return 0
    for key in rows[0].keys():
        vals = numeric(row.get(key) for row in rows)
        if vals and len(vals) == len(rows):
            print(f"{key}: min={min(vals):.4g} mean={mean(vals):.4g} max={max(vals):.4g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
