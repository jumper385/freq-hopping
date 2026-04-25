"""
Real-time OFDM monitor.

Continuously transmits a burst (cyclic TX), receives, demodulates, and
updates a live 3-panel plot:
  - Left  : scrolling I/Q waveform with P1/P2/data-start markers
  - Centre: ZC correlation magnitude + adaptive threshold
  - Right : live constellation (last N_HISTORY bursts fading by age)

Press Ctrl-C to stop.
"""

import signal
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from collections import deque

from src.OFDM import OFDM
from src.PlutoSDR import PlutoSDR

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CP_LEN      = 64
ROLL_OFF    = 8
N_SYMS      = 10
N_HISTORY   = 8       # number of past bursts kept in the constellation
UPDATE_MS   = 50      # target plot refresh interval in milliseconds

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
ofdm = OFDM(cp_len=CP_LEN, roll_off=ROLL_OFF)

pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
pilot_mask[::8] = True
data_tones = int(np.count_nonzero(~pilot_mask))

rx_sdr = PlutoSDR(uri="usb:", rx_gain=30)
tx_sdr = PlutoSDR(uri="ip:192.168.8.93", tx_gain=0)

rng = np.random.default_rng(64)
symbols_matrix = (
    rng.choice([-1, 1], size=(N_SYMS, data_tones))
    + 1j * rng.choice([-1, 1], size=(N_SYMS, data_tones))
).astype(complex)

burst = ofdm.modulate_burst(symbols_matrix)
print(f"Burst: {N_SYMS} symbols × {data_tones} data tones — {len(burst)} samples")
print("Transmitting (cyclic) ...  Press Ctrl-C to stop.\n")
tx_sdr.transmit(burst)

# ---------------------------------------------------------------------------
# Figure setup
# ---------------------------------------------------------------------------
plt.ion()
fig = plt.figure(figsize=(18, 5))
gs  = gridspec.GridSpec(1, 3, figure=fig)

ax_iq   = fig.add_subplot(gs[0])
ax_corr = fig.add_subplot(gs[1])
ax_const = fig.add_subplot(gs[2])

ax_iq.set_title("Received I/Q waveform")
ax_iq.set_xlabel("Sample")
ax_corr.set_title("ZC correlation + threshold")
ax_corr.set_xlabel("Sample")
ax_const.set_title(f"Live constellation (last {N_HISTORY} bursts)")
ax_const.set_xlabel("I")
ax_const.set_ylabel("Q")
ax_const.set_aspect("equal")
ax_const.axhline(0, color="k", linewidth=0.4)
ax_const.axvline(0, color="k", linewidth=0.4)

# pre-create artists so we update data instead of re-drawing from scratch
line_i,  = ax_iq.plot([], [], linewidth=0.6, label="I")
line_q,  = ax_iq.plot([], [], linewidth=0.6, label="Q")
vline_p1   = ax_iq.axvline(np.nan, color="orange", linewidth=1.2, linestyle="--", label="P1")
vline_p2   = ax_iq.axvline(np.nan, color="red",    linewidth=1.2, linestyle="--", label="P2")
vline_data = ax_iq.axvline(np.nan, color="lime",   linewidth=1.5, linestyle="-",  label="data start")
dot_data,  = ax_iq.plot([], [], "v", color="lime", markersize=8)
ax_iq.legend(fontsize=7)

line_corr, = ax_corr.plot([], [], linewidth=0.6, color="steelblue", label="|corr|")
hline_thr  = ax_corr.axhline(0, color="r", linewidth=1.0, linestyle="--", label="threshold")
ax_corr.legend(fontsize=7)

# constellation history: deque of scatter artists, oldest first
const_scatters: deque = deque(maxlen=N_HISTORY)

plt.tight_layout()
fig.canvas.draw()

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
def _shutdown(sig, frame):
    print("\nStopping ...")
    tx_sdr.stop_transmit()
    plt.ioff()
    plt.close("all")
    sys.exit(0)

signal.signal(signal.SIGINT, _shutdown)

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
iteration = 0
ser_accumulator = []

while True:
    y = rx_sdr.receive()

    # --- demodulate ---
    recovered = ofdm.demodulate_burst(y, N_SYMS)

    # --- debug info ---
    y_cfo = ofdm._cancel_cfo(y)
    corr_mag, threshold = ofdm._correlate(y_cfo)
    peaks = ofdm._preamble_detect(y_cfo)
    pair  = ofdm._find_preamble_pair(peaks)

    # SER
    tx_flat  = symbols_matrix.flatten()
    rx_flat  = recovered.flatten()
    dec_rx   = np.sign(rx_flat.real)  + 1j * np.sign(rx_flat.imag)
    dec_tx   = np.sign(tx_flat.real)  + 1j * np.sign(tx_flat.imag)
    ser      = float(np.mean(dec_rx != dec_tx))
    ser_accumulator.append(ser)
    mean_ser = np.mean(ser_accumulator[-20:])   # rolling 20-burst average

    iteration += 1
    status = f"iter={iteration:4d}  peaks={len(peaks):3d}  pair={'✓' if pair else '✗'}  SER={ser:.1%}  avg={mean_ser:.1%}"
    if not pair:
        status += "  [WARNING: no valid pair]"
    print(status)

    # --- update I/Q waveform ---
    x_axis = np.arange(len(y))
    line_i.set_data(x_axis, y.real)
    line_q.set_data(x_axis, y.imag)
    ax_iq.set_xlim(0, len(y))
    ymax = np.max(np.abs(y)) * 1.1 or 1.0
    ax_iq.set_ylim(-ymax, ymax)

    if pair:
        frame_start = pair[1] + 32
        vline_p1.set_xdata([pair[0], pair[0]])
        vline_p2.set_xdata([pair[1], pair[1]])
        vline_data.set_xdata([frame_start, frame_start])
        dot_data.set_data([frame_start], [float(y.real[frame_start])])
    else:
        for v in (vline_p1, vline_p2, vline_data):
            v.set_xdata([np.nan, np.nan])
        dot_data.set_data([], [])

    # --- update correlation plot ---
    c_axis = np.arange(len(corr_mag))
    line_corr.set_data(c_axis, corr_mag)
    hline_thr.set_ydata([threshold, threshold])
    ax_corr.set_xlim(0, len(corr_mag))
    ax_corr.set_ylim(0, max(corr_mag.max(), threshold) * 1.15)

    # --- update constellation (fade older bursts) ---
    flat = recovered.flatten()
    # fade existing scatters
    for idx, sc in enumerate(const_scatters):
        alpha = (idx + 1) / N_HISTORY * 0.5   # oldest ~0.05, newest 0.5
        sc.set_alpha(alpha)
    # add new scatter
    sc_new = ax_const.scatter(flat.real, flat.imag, s=12, alpha=0.8,
                              color="steelblue")
    const_scatters.append(sc_new)
    # remove scatters that were pushed out of the deque
    for artist in ax_const.collections:
        if artist not in const_scatters:
            artist.remove()

    clim = 3.5
    ax_const.set_xlim(-clim, clim)
    ax_const.set_ylim(-clim, clim)
    ax_const.set_title(f"Live constellation — SER {mean_ser:.1%} (20-burst avg)")

    fig.canvas.draw_idle()
    plt.pause(UPDATE_MS / 1000)
