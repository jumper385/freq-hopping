#!/usr/bin/env python3
"""Frequency-hop OFDM smoke loop for a TX/RX PlutoSDR pair.

This is the bridge between fixed-link smoke tests and MAB control. It retunes
both radios across a supplied channel list, sends the same burst cyclically, and
logs SER/timing per hop. Start with high TX attenuation, e.g. --tx-gain -60.
"""
import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.OFDM import OFDM
from src.PlutoSDR import PlutoSDR


def qpsk_decide(x: np.ndarray) -> np.ndarray:
    return np.sign(x.real) + 1j * np.sign(x.imag)


def make_payload(ofdm: OFDM, n_symbols: int, seed: int) -> np.ndarray:
    pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
    pilot_mask[::8] = True
    data_tones = int(np.count_nonzero(~pilot_mask))
    rng = np.random.default_rng(seed)
    return (
        rng.choice([-1, 1], size=(n_symbols, data_tones))
        + 1j * rng.choice([-1, 1], size=(n_symbols, data_tones))
    ).astype(complex)


def parse_freqs(text: str) -> list[int]:
    return [int(part.strip()) for part in text.split(",") if part.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tx-uri", required=True)
    p.add_argument("--rx-uri", required=True)
    p.add_argument("--freqs", default="914000000,915000000,916000000")
    p.add_argument("--sample-rate", type=int, default=1_000_000)
    p.add_argument("--tx-gain", type=int, default=-60)
    p.add_argument("--rx-gain", type=int, default=30)
    p.add_argument("--buffer-size", type=int, default=16_384)
    p.add_argument("--hops", type=int, default=30)
    p.add_argument("--symbols", type=int, default=10)
    p.add_argument("--settle-ms", type=float, default=5.0)
    p.add_argument("--seed", type=int, default=123)
    p.add_argument("--out", default="results/fh_loop.csv")
    args = p.parse_args()

    freqs = parse_freqs(args.freqs)
    ofdm = OFDM(cp_len=16, roll_off=8)
    payload = make_payload(ofdm, args.symbols, args.seed)
    burst = ofdm.modulate_burst(payload)
    tx_dec = qpsk_decide(payload.flatten())

    tx = PlutoSDR(args.tx_uri, center_freq=freqs[0], sample_rate=args.sample_rate,
                  tx_gain=args.tx_gain, rx_gain=args.rx_gain, buffer_size=args.buffer_size)
    rx = PlutoSDR(args.rx_uri, center_freq=freqs[0], sample_rate=args.sample_rate,
                  tx_gain=args.tx_gain, rx_gain=args.rx_gain, buffer_size=args.buffer_size)

    rows = []
    try:
        tx.transmit(burst)
        time.sleep(0.1)
        for hop in range(args.hops):
            freq = freqs[hop % len(freqs)]
            t0 = time.perf_counter_ns()
            tx.tune(freq)
            rx.tune(freq)
            t1 = time.perf_counter_ns()
            time.sleep(args.settle_ms / 1000.0)
            y = rx.receive()
            t2 = time.perf_counter_ns()
            recovered = ofdm.demodulate_burst(y, args.symbols)
            t3 = time.perf_counter_ns()
            rx_dec = qpsk_decide(recovered.flatten())
            ser = float(np.mean(rx_dec != tx_dec))
            peaks = ofdm._preamble_detect(ofdm._cancel_cfo(y))
            row = {
                "hop": hop,
                "freq_hz": freq,
                "ser": ser,
                "peaks": len(peaks),
                "retune_ms": (t1 - t0) / 1e6,
                "capture_ms": (t2 - t1) / 1e6,
                "demod_ms": (t3 - t2) / 1e6,
            }
            rows.append(row)
            print(
                f"hop {hop:03d} {freq/1e6:.3f} MHz: "
                f"SER={ser:.2%}, peaks={len(peaks)}, "
                f"retune={row['retune_ms']:.2f} ms"
            )
    finally:
        try:
            tx.stop_transmit()
        except Exception:
            pass

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
