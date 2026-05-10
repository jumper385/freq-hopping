#!/usr/bin/env python3
"""Fixed-frequency PlutoSDR OFDM smoke test for a TX/RX pair."""
import argparse
import csv
import time
from pathlib import Path

import numpy as np

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.OFDM import OFDM
from src.PlutoSDR import PlutoSDR


def qpsk_decide(x):
    return np.sign(x.real) + 1j * np.sign(x.imag)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tx-uri", required=True)
    p.add_argument("--rx-uri", required=True)
    p.add_argument("--freq", type=int, default=915_000_000)
    p.add_argument("--sample-rate", type=int, default=1_000_000)
    p.add_argument("--tx-gain", type=int, default=-60, help="Pluto TX attenuation dB; start conservative")
    p.add_argument("--rx-gain", type=int, default=30)
    p.add_argument("--bursts", type=int, default=20)
    p.add_argument("--symbols", type=int, default=10)
    p.add_argument("--out", default="results/link_smoke_test.csv")
    args = p.parse_args()

    ofdm = OFDM(cp_len=16, roll_off=8)
    data_tones = ofdm.data_tone_count

    tx = PlutoSDR(args.tx_uri, center_freq=args.freq, sample_rate=args.sample_rate, tx_gain=args.tx_gain, rx_gain=args.rx_gain)
    rx = PlutoSDR(args.rx_uri, center_freq=args.freq, sample_rate=args.sample_rate, tx_gain=args.tx_gain, rx_gain=args.rx_gain)

    rng = np.random.default_rng(123)
    payload = (rng.choice([-1, 1], size=(args.symbols, data_tones)) + 1j * rng.choice([-1, 1], size=(args.symbols, data_tones))).astype(complex)
    burst = ofdm.modulate_burst(payload)
    tx.transmit(burst)
    time.sleep(0.1)

    rows = []
    try:
        for i in range(args.bursts):
            t0 = time.perf_counter_ns()
            y = rx.receive()
            recovered = ofdm.demodulate_burst(y, args.symbols)
            dt_ms = (time.perf_counter_ns() - t0) / 1e6
            ser = float(np.mean(qpsk_decide(recovered.flatten()) != qpsk_decide(payload.flatten())))
            peaks = ofdm._preamble_detect(ofdm._cancel_cfo(y))
            rows.append({"burst": i, "ser": ser, "capture_demod_ms": dt_ms, "peaks": len(peaks)})
            print(f"burst {i:03d}: SER={ser:.2%}, capture+demod={dt_ms:.2f} ms, peaks={len(peaks)}")
    finally:
        tx.stop_transmit()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
