#!/usr/bin/env python3
"""Measure PlutoSDR LO retune + optional RX capture timing.

This is a host-side timing benchmark. It does not prove RF settling, but it gives
an early budget for the Python/libiio control loop.
"""
import argparse
import csv
import time
from pathlib import Path

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.PlutoSDR import PlutoSDR


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--uri", required=True)
    p.add_argument("--freq", type=int, nargs="+", default=[914_000_000, 915_000_000, 916_000_000])
    p.add_argument("--sample-rate", type=int, default=1_000_000)
    p.add_argument("--rx-gain", type=int, default=30)
    p.add_argument("--tx-gain", type=int, default=-60)
    p.add_argument("--buffer-size", type=int, default=16_384)
    p.add_argument("--loops", type=int, default=50)
    p.add_argument("--capture", action="store_true", help="also capture one RX buffer after each retune")
    p.add_argument("--out", default="results/retune_benchmark.csv")
    args = p.parse_args()

    sdr = PlutoSDR(
        uri=args.uri,
        center_freq=args.freq[0],
        sample_rate=args.sample_rate,
        rx_gain=args.rx_gain,
        tx_gain=args.tx_gain,
        buffer_size=args.buffer_size,
    )

    rows = []
    for i in range(args.loops):
        freq = args.freq[i % len(args.freq)]
        t0 = time.perf_counter_ns()
        sdr.tune(freq)
        t1 = time.perf_counter_ns()
        if args.capture:
            sdr.receive(flush=0)
        t2 = time.perf_counter_ns()
        rows.append({
            "i": i,
            "freq_hz": freq,
            "retune_ms": (t1 - t0) / 1e6,
            "retune_capture_ms": (t2 - t0) / 1e6,
            "capture": args.capture,
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    retunes = [r["retune_ms"] for r in rows]
    print(f"retune ms: min={min(retunes):.3f} mean={sum(retunes)/len(retunes):.3f} max={max(retunes):.3f}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
