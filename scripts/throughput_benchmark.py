#!/usr/bin/env python3
"""Measure end-to-end SDR link throughput.

Fixed-frequency OFDM/QPSK burst tests across configurable burst sizes, FFT
sizes, CP lengths, and windowing.  Logs per-burst validity, SER, timing, and
effective goodput (valid payload bits / real elapsed wall time).

Run from the repo root::

    python scripts/throughput_benchmark.py --tx-uri usb: --rx-uri ip:192.168.8.93

Test a sweep::

    python scripts/throughput_benchmark.py --tx-uri usb: --rx-uri ip:192.168.8.93 \\
        --sweep bursts=1,5,10,20,50 --per-config 8 --tx-gain -30

Single quick spot check (no sweep)::

    python scripts/throughput_benchmark.py --tx-uri usb: --rx-uri ip:192.168.8.93 \\
        --bursts 10 --per-config 20 --freq 915e6 --tx-gain -30

Dry-run (no SDR, just print framing numbers)::

    python scripts/throughput_benchmark.py --dry-run
"""
import argparse
import csv
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from src.OFDM import OFDM
from src.PlutoSDR import PlutoSDR


QPSK_MAP = np.array([1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j], dtype=complex)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def qpsk_decide(x):
    return np.sign(x.real) + 1j * np.sign(x.imag)


def qpsk_payload(ofdm: OFDM, n_symbols: int, seed: int):
    rng = np.random.default_rng(seed)
    return rng.choice(QPSK_MAP, size=(n_symbols, ofdm.data_tone_count))


@dataclass
class AcquisitionMeta:
    valid: bool
    p1: int | None = None
    p2: int | None = None
    peak_count: int = 0
    peak_margin: float = 0.0
    cfo_norm: float = 0.0
    reason: str = ""


def acquire(ofdm: OFDM, y: np.ndarray, min_margin: float = 2.5) -> AcquisitionMeta:
    """Acquire preamble and return validity metadata.

    *min_margin* is the peak‑max / threshold ratio required for a valid lock.
    Below this the packet is considered un‑acquired and the burst should be
    rejected before computing SER/reward.
    """
    y_cfo = ofdm._cancel_cfo(y)
    corr_mag, threshold = ofdm._correlate(y_cfo)
    peaks = ofdm._preamble_detect(y_cfo)
    pair = ofdm._find_preamble_pair(peaks)
    peak_max = float(np.max(corr_mag)) if len(corr_mag) else 0.0
    margin = peak_max / float(threshold) if threshold > 0 else 0.0

    if pair is None and len(peaks) < 1:
        return AcquisitionMeta(valid=False, peak_count=len(peaks), peak_margin=margin,
                               reason="no peaks")
    if pair is None:
        return AcquisitionMeta(valid=False, peak_count=len(peaks), peak_margin=margin,
                               reason=f"no valid P1/P2 pair ({len(peaks)} peaks)")
    if margin < min_margin:
        return AcquisitionMeta(valid=False, p1=pair[0], p2=pair[1],
                               peak_count=len(peaks), peak_margin=margin,
                               reason=f"low margin {margin:.2f} < {min_margin}")

    # CFO from the pair we used
    preamble_len = 32
    r1 = y_cfo[pair[0]: pair[0] + preamble_len]
    r2 = y_cfo[pair[1]: pair[1] + preamble_len]
    phi = np.angle(np.sum(r2 * np.conj(r1)))
    cfo_norm = phi / (2 * np.pi * preamble_len)

    return AcquisitionMeta(valid=True, p1=pair[0], p2=pair[1],
                           peak_count=len(peaks), peak_margin=margin,
                           cfo_norm=cfo_norm, reason="ok")


def parse_sweep(expr: str) -> list[int]:
    """Parse ``param=val1,val2,...`` into a list of ints."""
    _, _, values = expr.partition("=")
    return [int(v.strip()) for v in values.split(",") if v.strip()]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="SDR throughput benchmark")
    p.add_argument("--tx-uri", help="Pluto TX URI (skip for dry-run)")
    p.add_argument("--rx-uri", help="Pluto RX URI (skip for dry-run)")
    p.add_argument("--freq", type=float, default=915e6)
    p.add_argument("--sample-rate", type=int, default=1_000_000)
    p.add_argument("--tx-gain", type=int, default=-40)
    p.add_argument("--rx-gain", type=int, default=30)
    p.add_argument("--buffer-size", type=int, default=16_384)
    p.add_argument("--bursts", type=int, default=10,
                   help="OFDM symbols per burst")
    p.add_argument("--n-tones", type=int, default=50)
    p.add_argument("--cp-len", type=int, default=16)
    p.add_argument("--roll-off", type=int, default=0)
    p.add_argument("--per-config", type=int, default=20,
                   help="iterations per configuration")
    p.add_argument("--min-margin", type=float, default=2.5,
                   help="min ZC peak/threshold ratio for valid lock")
    p.add_argument("--sweep", action="append", default=[],
                   help="param=val1,...,valN sweep (e.g. bursts=1,5,10,20)")
    p.add_argument("--out", default="results/throughput_benchmark.csv")
    p.add_argument("--dry-run", action="store_true",
                   help="print theoretical framing only, no SDR")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    # --- build config grid ---
    sweep_map: dict[str, list[int]] = {}
    for expr in args.sweep:
        parts = expr.partition("=")
        key = parts[0].strip()
        vals = [int(x.strip()) for x in parts[2].split(",") if x.strip()]
        if key in ("bursts", "n_tones", "cp_len", "roll_off"):
            sweep_map[key] = vals
        else:
            print(f"ignoring unknown sweep key '{key}'", file=sys.stderr)

    if not sweep_map:
        configs = [dict(bursts=args.bursts, n_tones=args.n_tones,
                        cp_len=args.cp_len, roll_off=args.roll_off)]
    else:
        import itertools
        keys = list(sweep_map)
        combos = list(itertools.product(*(sweep_map[k] for k in keys)))
        configs = []
        base = dict(bursts=args.bursts, n_tones=args.n_tones,
                    cp_len=args.cp_len, roll_off=args.roll_off)
        for combo in combos:
            cfg = dict(base)
            for k, v in zip(keys, combo):
                cfg[k] = v
            configs.append(cfg)

    # --- dry-run: print theoretical framing only ---
    if args.dry_run:
        print(f"{'bursts':>7} {'n_tones':>7} {'cp':>4} {'ro':>4} {'data_t':>6} "
              f"{'frame_smp':>9} {'ideal_qpsk_mbps':>15}")
        print("-" * 70)
        for cfg in configs:
            o = OFDM(n_tones=cfg["n_tones"], cp_len=cfg["cp_len"], roll_off=cfg["roll_off"])
            tp = o.theoretical_throughput_bps(args.sample_rate, 2, cfg["bursts"])
            print(f"{cfg['bursts']:>7} {cfg['n_tones']:>7} {cfg['cp_len']:>4} "
                  f"{cfg['roll_off']:>4} {o.data_tone_count:>6} "
                  f"{o.frame_len(cfg['bursts']):>9} {tp/1e6:>15.6f}")
        return 0

    # --- SDR mode: connect + test ---
    if not args.tx_uri or not args.rx_uri:
        print("SDR mode requires --tx-uri and --rx-uri", file=sys.stderr)
        return 1

    print("Connecting …")
    tx = PlutoSDR(args.tx_uri, center_freq=int(args.freq),
                  sample_rate=args.sample_rate, tx_gain=args.tx_gain,
                  rx_gain=args.rx_gain, buffer_size=args.buffer_size)
    rx = PlutoSDR(args.rx_uri, center_freq=int(args.freq),
                  sample_rate=args.sample_rate, tx_gain=args.tx_gain,
                  rx_gain=args.rx_gain, buffer_size=args.buffer_size)
    print(f"  TX: {args.tx_uri}  RX: {args.rx_uri}  freq={args.freq/1e6:.3f} MHz")
    print()

    rows: list[dict] = []
    total_configs = len(configs) * args.per_config

    header = ("# cfg  bursts n_tones cp ro  iter  valid  ser  margin  "
              "cfo_hz  wall_ms  goodput_mbps  frame_smp  ideal_mbps")
    print(header.replace("# ", ""))

    row_idx = 0
    for ci, cfg in enumerate(configs):
        ofdm = OFDM(n_tones=cfg["n_tones"], cp_len=cfg["cp_len"],
                    roll_off=cfg["roll_off"])
        payload = qpsk_payload(ofdm, cfg["bursts"], args.seed)
        tx_dec = qpsk_decide(payload.flatten())
        ideal_mbps = ofdm.theoretical_throughput_bps(args.sample_rate, 2,
                                                     cfg["bursts"]) / 1e6
        burst = ofdm.modulate_burst(payload)
        frame_smp = len(burst)

        tx.transmit(burst)
        time.sleep(0.15)

        for rep in range(args.per_config):
            t0 = time.perf_counter()
            y = rx.receive()
            t_cap = time.perf_counter()

            meta = acquire(ofdm, y, min_margin=args.min_margin)

            if meta.valid:
                recovered = ofdm.demodulate_burst(y, cfg["bursts"])
                rx_dec = qpsk_decide(recovered.flatten())
                ser = float(np.mean(rx_dec != tx_dec))
            else:
                ser = 1.0

            t1 = time.perf_counter()
            wall_ms = (t1 - t0) * 1000
            payload_bits = ofdm.payload_bits_per_frame(2, cfg["bursts"])
            goodput = 0.0
            if meta.valid:
                goodput = payload_bits * (1.0 - ser) / (t1 - t0)

            row = dict(
                config=ci, bursts=cfg["bursts"], n_tones=cfg["n_tones"],
                cp_len=cfg["cp_len"], roll_off=cfg["roll_off"],
                iteration=rep, valid=meta.valid, ser=ser,
                peak_count=meta.peak_count, peak_margin=meta.peak_margin,
                cfo_norm=meta.cfo_norm,
                cfo_hz=meta.cfo_norm * args.sample_rate,
                wall_ms=wall_ms,
                goodput_mbps=goodput / 1e6,
                frame_samples=frame_smp,
                ideal_mbps=ideal_mbps,
                reason=meta.reason,
                p1=meta.p1 or "", p2=meta.p2 or "",
                tx_gain=args.tx_gain, freq_mhz=args.freq / 1e6,
            )
            rows.append(row)

            tag = "OK" if meta.valid else "INV"
            print(f"  {ci:3d} {cfg['bursts']:>6} {cfg['n_tones']:>6} "
                  f"{cfg['cp_len']:>3} {cfg['roll_off']:>2}  "
                  f"{rep:>4d}  {tag:>3s}  {ser:.3f}  {meta.peak_margin:>5.1f}  "
                  f"{meta.cfo_norm * args.sample_rate:>+7.0f}  "
                  f"{wall_ms:>7.2f}  {goodput/1e6:>11.6f}  "
                  f"{frame_smp:>9}  {ideal_mbps:>10.6f}")

            row_idx += 1

        tx.stop_transmit()
        time.sleep(0.05)

    # --- summary ---
    valid_rows = [r for r in rows if r["valid"]]
    print(f"\n--- Summary ---")
    print(f"  Total trials:         {len(rows)}")
    print(f"  Valid locks:          {len(valid_rows)}/{len(rows)} "
          f"({100*len(valid_rows)/len(rows):.1f}%)")
    if valid_rows:
        med_goodput = np.median([r["goodput_mbps"] for r in valid_rows])
        med_wall = np.median([r["wall_ms"] for r in valid_rows])
        print(f"  Median goodput:       {med_goodput:.6f} Mbit/s")
        print(f"  Median wall time:     {med_wall:.2f} ms")
        print(f"  Mean SER (valid):     {np.mean([r['ser'] for r in valid_rows]):.4f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    field_names = list(rows[0])
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=field_names)
        w.writeheader()
        w.writerows(rows)
    print(f"  CSV → {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
