#!/usr/bin/env python3
"""Live PlutoSDR frequency-hopping loop driven by a MAB agent.

Reward is currently derived from measured QPSK symbol error rate:
    reward = clip(1 - SER, 0, 1)

This is intentionally simple and thesis-friendly: the same loop can later swap
SER for PER/ACK/SINR/composite reward without changing the agent interface.
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
from src.fh.agents import EXP3Agent, RandomAgent, StaticAgent, ThompsonSamplingAgent, UCBAgent


def parse_freqs(text: str) -> list[int]:
    return [int(part.strip()) for part in text.split(",") if part.strip()]


def qpsk_decide(x: np.ndarray) -> np.ndarray:
    return np.sign(x.real) + 1j * np.sign(x.imag)


def make_payload(ofdm: OFDM, n_symbols: int, seed: int) -> np.ndarray:
    data_tones = ofdm.data_tone_count
    rng = np.random.default_rng(seed)
    return (
        rng.choice([-1, 1], size=(n_symbols, data_tones))
        + 1j * rng.choice([-1, 1], size=(n_symbols, data_tones))
    ).astype(complex)


def make_agent(name: str, n_arms: int, seed: int):
    if name == "static":
        return StaticAgent(0)
    if name == "random":
        return RandomAgent(n_arms, seed=seed)
    if name == "ucb":
        return UCBAgent(n_arms)
    if name == "ts":
        return ThompsonSamplingAgent(n_arms, seed=seed)
    if name == "exp3":
        return EXP3Agent(n_arms, seed=seed)
    raise ValueError(f"unknown agent: {name}")


def corr_metrics(ofdm: OFDM, y: np.ndarray) -> dict:
    y_cfo = ofdm._cancel_cfo(y)
    corr_mag, threshold = ofdm._correlate(y_cfo)
    peaks = ofdm._preamble_detect(y_cfo)
    pair = ofdm._find_preamble_pair(peaks)
    peak_max = float(np.max(corr_mag)) if len(corr_mag) else 0.0
    return {
        "peaks": len(peaks),
        "threshold": float(threshold),
        "peak_max": peak_max,
        "peak_margin": peak_max / float(threshold) if threshold else 0.0,
        "p1": pair[0] if pair else "",
        "p2": pair[1] if pair else "",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tx-uri", required=True)
    p.add_argument("--rx-uri", required=True)
    p.add_argument("--freqs", default="914000000,915000000,916000000")
    p.add_argument("--agent", choices=["static", "random", "ucb", "ts", "exp3"], default="ucb")
    p.add_argument("--sample-rate", type=int, default=1_000_000)
    p.add_argument("--tx-gain", type=int, default=0, help="TX hardware gain dB; 0=full power for OTA")
    p.add_argument("--rx-gain", type=int, default=30)
    p.add_argument("--buffer-size", type=int, default=16_384)
    p.add_argument("--hops", type=int, default=30)
    p.add_argument("--symbols", type=int, default=10)
    p.add_argument("--settle-ms", type=float, default=5.0)
    p.add_argument("--seed", type=int, default=123)
    p.add_argument("--out", default="results/live_mab_loop.csv")
    args = p.parse_args()

    freqs = parse_freqs(args.freqs)
    ofdm = OFDM(cp_len=16, roll_off=8)
    payload = make_payload(ofdm, args.symbols, args.seed)
    burst = ofdm.modulate_burst(payload)
    tx_dec = qpsk_decide(payload.flatten())
    agent = make_agent(args.agent, len(freqs), args.seed)

    tx = PlutoSDR(args.tx_uri, center_freq=freqs[0], sample_rate=args.sample_rate,
                  tx_gain=args.tx_gain, rx_gain=args.rx_gain, buffer_size=args.buffer_size)
    rx = PlutoSDR(args.rx_uri, center_freq=freqs[0], sample_rate=args.sample_rate,
                  tx_gain=args.tx_gain, rx_gain=args.rx_gain, buffer_size=args.buffer_size)

    rows = []
    cumulative_reward = 0.0
    try:
        tx.transmit(burst)
        time.sleep(0.1)
        for hop in range(args.hops):
            arm = agent.select()
            freq = freqs[arm]
            t0 = time.perf_counter_ns()
            tx.tune(freq)
            rx.tune(freq)
            t1 = time.perf_counter_ns()
            time.sleep(args.settle_ms / 1000.0)
            y = rx.receive()
            t2 = time.perf_counter_ns()
            metrics = corr_metrics(ofdm, y)
            valid = True
            error = ""
            try:
                recovered = ofdm.demodulate_burst(y, args.symbols)
                rx_dec = qpsk_decide(recovered.flatten())
                ser = float(np.mean(rx_dec != tx_dec))
                reward = float(np.clip(1.0 - ser, 0.0, 1.0))
            except Exception as exc:
                valid = False
                error = type(exc).__name__
                ser = 1.0
                reward = 0.0
            t3 = time.perf_counter_ns()

            agent.update(arm, reward)
            cumulative_reward += reward

            row = {
                "hop": hop,
                "agent": args.agent,
                "arm": arm,
                "freq_hz": freq,
                "valid": valid,
                "error": error,
                "ser": ser,
                "reward": reward,
                "cumulative_reward": cumulative_reward,
                "retune_ms": (t1 - t0) / 1e6,
                "capture_ms": (t2 - t1) / 1e6,
                "demod_ms": (t3 - t2) / 1e6,
                **metrics,
            }
            rows.append(row)
            status = "ok" if valid else f"invalid:{error}"
            print(
                f"hop {hop:03d} {args.agent} arm={arm} {freq/1e6:.3f} MHz: "
                f"{status}, SER={ser:.2%}, reward={reward:.3f}, margin={metrics['peak_margin']:.2f}"
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
