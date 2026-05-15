"""
Pure simulation utilities for preamble performance characterisation.

All functions are side-effect free: they accept a Modem and an RNG and
return data structures — no printing, no plotting.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))   # repo root

import numpy as np
from src.modem import Modem, SyncDebug


def awgn(signal: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Add complex AWGN to *signal* at the requested SNR (dB)."""
    power = np.mean(np.abs(signal) ** 2)
    n0 = power / (10 ** (snr_db / 10))
    noise = np.sqrt(n0 / 2) * (
        rng.standard_normal(len(signal)) + 1j * rng.standard_normal(len(signal))
    )
    return signal + noise


def sweep_detection_rate(
    modem: Modem,
    burst: np.ndarray,
    snr_range: np.ndarray,
    n_trials: int,
    rng: np.random.Generator,
    verbose: bool = False,
) -> list[float]:
    """Return detection probability at each SNR in *snr_range*."""
    rates = []
    for snr in snr_range:
        hits = sum(
            modem.sync_debug(awgn(burst, snr, rng)).pair is not None
            for _ in range(n_trials)
        )
        rates.append(hits / n_trials)
        if verbose:
            print(f"  SNR={snr:+4.0f} dB  P_det={rates[-1]:.1%}")
    return rates


def measure_false_alarm_rate(
    modem: Modem,
    burst_len: int,
    n_trials: int,
    rng: np.random.Generator,
    noise_snr_db: float = 0.0,
) -> float:
    """Return false-alarm rate on pure-noise input of length *burst_len*."""
    noise_only = np.zeros(burst_len, dtype=complex)
    triggers = sum(
        modem.sync_debug(awgn(noise_only, noise_snr_db, rng)).pair is not None
        for _ in range(n_trials)
    )
    return triggers / n_trials


def collect_snapshot(
    modem: Modem,
    burst: np.ndarray,
    snr_db: float,
    rng: np.random.Generator,
) -> SyncDebug:
    """Run sync_debug on a single noisy burst and return the debug struct."""
    return modem.sync_debug(awgn(burst, snr_db, rng))


def collect_margins(
    modem: Modem,
    burst: np.ndarray,
    snr_list: list[int],
    n_trials: int,
    rng: np.random.Generator,
) -> dict[int, list[float]]:
    """Return peak-margin samples (|corr|_max / threshold) per SNR level."""
    margins: dict[int, list[float]] = {s: [] for s in snr_list}
    for snr in snr_list:
        for _ in range(n_trials):
            dbg = modem.sync_debug(awgn(burst, snr, rng))
            if len(dbg.corr_mag) and dbg.threshold > 0:
                margin = float(np.max(np.abs(dbg.corr_mag))) / dbg.threshold
                margins[snr].append(margin)
    return margins
