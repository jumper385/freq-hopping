"""
Preamble performance visualiser — development tool.

Run from the repo root:
    python scripts/preamble_dev.py

Three panels:
  Top-left  : Detection rate vs SNR, with false-alarm rate as a dashed baseline.
  Top-right : Correlation snapshot at SNAPSHOT_SNR_DB — shows the raw |corr|
              envelope, adaptive threshold, and detected peak positions.
  Bottom    : Peak-margin distributions at several SNR levels.

Tweak the CONFIG block to explore different preamble lengths, ZC roots,
threshold multipliers, and SNR ranges.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))   # repo root
sys.path.insert(0, str(Path(__file__).parent))          # scripts/

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from src.preamble_modem import PreambleModem
from preamble_sim import (
    sweep_detection_rate,
    measure_false_alarm_rate,
    collect_snapshot,
    collect_margins,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PREAMBLE_LEN    = 32
SILENCE_LEN     = 32
N_TRIALS        = 400
SNR_RANGE       = np.arange(-15, 26, 2)   # dB
SNAPSHOT_SNR_DB = 5
MARGIN_SNRS     = [-5, 0, 5, 10, 20]
RNG_SEED        = 0
# ---------------------------------------------------------------------------

rng   = np.random.default_rng(RNG_SEED)
modem = PreambleModem(preamble_len=PREAMBLE_LEN, silence_len=SILENCE_LEN)
burst = modem.modulate_burst(np.empty((1, 0), dtype=complex))

print(f"Burst length : {len(burst)} samples")
print(f"Preamble len : {PREAMBLE_LEN}")
print(f"Trials/point : {N_TRIALS}")
print(f"SNR range    : {SNR_RANGE[0]} … {SNR_RANGE[-1]} dB\n")

# ---------------------------------------------------------------------------
# Run simulations
# ---------------------------------------------------------------------------
print("Sweeping SNR ...")
det_rates = sweep_detection_rate(modem, burst, SNR_RANGE, N_TRIALS, rng, verbose=True)

print("\nMeasuring false-alarm rate ...")
far = measure_false_alarm_rate(modem, len(burst), N_TRIALS, rng)
print(f"  FAR = {far:.1%}  ({int(far * N_TRIALS)}/{N_TRIALS} triggers on noise)")

print(f"\nCollecting correlation snapshot at SNR={SNAPSHOT_SNR_DB:+d} dB ...")
dbg_snap = collect_snapshot(modem, burst, SNAPSHOT_SNR_DB, rng)

print("Collecting margin distributions ...")
margins = collect_margins(modem, burst, MARGIN_SNRS, N_TRIALS, rng)

# ---------------------------------------------------------------------------
# Plot results
# ---------------------------------------------------------------------------
fig = plt.figure(figsize=(16, 9))
gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.40, wspace=0.35)

ax_det  = fig.add_subplot(gs[0, 0])
ax_corr = fig.add_subplot(gs[0, 1])
ax_marg = fig.add_subplot(gs[1, :])

# --- detection rate ---
ax_det.plot(SNR_RANGE, det_rates, marker="o", markersize=4, linewidth=1.5,
            color="steelblue", label="P(detect)")
ax_det.axhline(far, color="tomato", linewidth=1.2, linestyle="--",
               label=f"FAR = {far:.1%}")
ax_det.axhline(0.99, color="gray", linewidth=0.8, linestyle=":",
               label="99 % ref")
ax_det.set_xlabel("SNR (dB)")
ax_det.set_ylabel("Rate")
ax_det.set_title(f"Detection rate vs SNR\n(preamble_len={PREAMBLE_LEN}, {N_TRIALS} trials)")
ax_det.set_ylim(-0.05, 1.10)
ax_det.legend(fontsize=8)
ax_det.grid(True, linewidth=0.4)

# --- correlation snapshot ---
if len(dbg_snap.corr_mag):
    c_ax = np.arange(len(dbg_snap.corr_mag))
    ax_corr.plot(c_ax, np.abs(dbg_snap.corr_mag), linewidth=0.8,
                 color="steelblue", label="|corr|")
    ax_corr.axhline(dbg_snap.threshold, color="tomato", linewidth=1.2,
                    linestyle="--", label=f"threshold ({dbg_snap.threshold:.3f})")
    if len(dbg_snap.peaks):
        ax_corr.scatter(dbg_snap.peaks,
                        np.abs(dbg_snap.corr_mag)[dbg_snap.peaks],
                        color="orange", zorder=5, s=30, label="peaks")
    if dbg_snap.pair:
        for p, lbl in zip(dbg_snap.pair, ("P1", "P2")):
            ax_corr.axvline(p, color="lime", linewidth=1.2, linestyle="-",
                            label=lbl)
ax_corr.set_xlabel("Sample")
ax_corr.set_ylabel("|corr|")
ax_corr.set_title(f"Correlation snapshot — SNR={SNAPSHOT_SNR_DB:+d} dB\n"
                  f"pair={'detected' if dbg_snap.pair else 'NOT detected'}")
ax_corr.legend(fontsize=8)
ax_corr.grid(True, linewidth=0.4)

# --- margin distributions ---
colors = plt.cm.viridis(np.linspace(0.2, 0.85, len(MARGIN_SNRS)))
for (snr, vals), color in zip(margins.items(), colors):
    if vals:
        ax_marg.hist(vals, bins=40, alpha=0.55, color=color,
                     label=f"SNR={snr:+d} dB", density=True)
ax_marg.axvline(1.0, color="tomato", linewidth=1.2, linestyle="--",
                label="threshold = 1×")
ax_marg.set_xlabel("Peak margin  (|corr|_max / threshold)")
ax_marg.set_ylabel("Density")
ax_marg.set_title("Peak-margin distribution — margin > 1.0 means detection triggered")
ax_marg.legend(fontsize=8)
ax_marg.grid(True, linewidth=0.4)

fig.suptitle(
    f"Preamble characterisation  ·  ZC length={PREAMBLE_LEN}  ·  "
    f"{N_TRIALS} trials/point",
    fontsize=12, y=0.98,
)

plt.savefig("preamble_dev.png", dpi=150, bbox_inches="tight")
print("\nSaved → preamble_dev.png")
plt.show()
