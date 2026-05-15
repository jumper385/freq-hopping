import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))   # repo root

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from src.preamble_modem import PreambleModem
from src.PlutoSDR import PlutoSDR

# PREAMBLE_LEN  = 32
SILENCE_LEN   = 64

TX_URI        = "ip:192.168.8.94"
RX_URI        = "ip:192.168.8.93"
CENTER_FREQ   = 915_000_000
SAMPLE_RATE   = 1_000_000
TX_GAIN       = 0
RX_GAIN       = 30
BUFFER_SIZE   = 4096
ADAPTIVE_THRESHOLD_MULTIPLIER = 5.0

N_CAPTURES    = 500     # RX buffers to analyse
FLUSH_BUFFERS = 10      # buffers discarded before capture starts
SNAPSHOT_IDX  = 10      # which capture index to use for the correlation panel
ROLLING_WIN   = 20      # window length for the rolling detection rate
# ---------------------------------------------------------------------------

fig, ax = plt.subplots(4, 4, figsize=(18, 5), sharex="col")

for preamble_idx, PREAMBLE_LEN in enumerate([16, 32, 64, 96]):
    modem = PreambleModem(preamble_len=PREAMBLE_LEN, silence_len=SILENCE_LEN, adaptive_threshold_multiplier=ADAPTIVE_THRESHOLD_MULTIPLIER)
    burst = modem.modulate_burst(np.empty((1, 0), dtype=complex))

    print(f"Burst length  : {len(burst)} samples")
    print(f"Preamble len  : {PREAMBLE_LEN}")
    print(f"Buffer size   : {BUFFER_SIZE} samples")
    print(f"Captures      : {N_CAPTURES}\n")

    # ---------------------------------------------------------------------------
    # Hardware setup
    # ---------------------------------------------------------------------------
    print("Connecting to SDRs ...")
    tx_sdr = PlutoSDR(
        uri=TX_URI,
        center_freq=CENTER_FREQ,
        sample_rate=SAMPLE_RATE,
        tx_gain=TX_GAIN,
        buffer_size=BUFFER_SIZE,
    )
    rx_sdr = PlutoSDR(
        uri=RX_URI,
        center_freq=CENTER_FREQ,
        sample_rate=SAMPLE_RATE,
        rx_gain=RX_GAIN,
        buffer_size=BUFFER_SIZE,
    )

    def _shutdown(sig, frame):
        print("\nStopping TX ...")
        tx_sdr.stop_transmit()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)

    print("Transmitting (cyclic) ...")
    tx_sdr.transmit(burst)

    # ---------------------------------------------------------------------------
    # Capture
    # ---------------------------------------------------------------------------
    print(f"Flushing {FLUSH_BUFFERS} RX buffers ...")
    rx_sdr.receive(flush=FLUSH_BUFFERS)

    detected: list[bool]  = []
    margins:  list[float] = []
    peak_diffs:  list[float] = []
    snapshot_dbg = None

    print(f"Capturing {N_CAPTURES} buffers ...")
    for i in range(N_CAPTURES):
        y   = rx_sdr.receive(flush=0)
        dbg = modem.sync_debug(y)

        detected.append(dbg.pair is not None)

        # if len(dbg.corr_mag) and dbg.threshold > 0:
        #     margins.append(float(np.max(np.abs(dbg.corr_mag))) / dbg.threshold)

        if i == SNAPSHOT_IDX:
            snapshot_dbg = dbg

        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{N_CAPTURES}  running P_det={sum(detected) / (i + 1):.1%}")

        if modem.dbg_instrument is not None:
            mean_margin = modem.dbg_instrument.get("mean_margin", None)
            margins.append(mean_margin)

            pair_spacings = modem.dbg_instrument.get("ave_pair_spacing", None)
            spacing_diffs = pair_spacings - PREAMBLE_LEN if pair_spacings is not None else None
            if spacing_diffs is not None:
                peak_diffs.append(spacing_diffs)


    tx_sdr.stop_transmit()
    print("TX stopped.\n")

    det_rate = sum(detected) / len(detected)
    print(f"P(detect) = {det_rate:.1%}  over {N_CAPTURES} captures")

    # ------------------------------------------------------------------
    # PLOTS
    # ------------------------------------------------------------------

    ax[preamble_idx][0].set_ylabel(f"N={PREAMBLE_LEN} Det={det_rate:.1%}\nADC_COUNTS")

    ax[preamble_idx][0].plot(y.real, label="I", color="gray", linewidth=0.5)
    ax[preamble_idx][0].plot(y.imag, label="Q", color="black", linewidth=0.5)

    ax[preamble_idx][1].set_ylabel("|Correlation|")
    ax[preamble_idx][1].plot(snapshot_dbg.corr_mag, label="|corr|", color="black", linewidth=0.5)
    ax[preamble_idx][1].axhline(snapshot_dbg.threshold, label="threshold", color="red", linestyle="--", linewidth=0.5)
    # show the detected peaks
    ax[preamble_idx][1].plot(snapshot_dbg.peaks, np.abs(snapshot_dbg.corr_mag)[snapshot_dbg.peaks], "x", label="peaks", color="blue")

    # show pairs
    for pair in snapshot_dbg.pair if snapshot_dbg.pair else []:
        ax[preamble_idx][1].axvline(pair[0], color="green", linestyle="-", linewidth=0.5)
        ax[preamble_idx][1].axvline(pair[1], color="orange", linestyle="-", linewidth=0.5)

    ax[preamble_idx][1].set_xlim(0, len(snapshot_dbg.corr_mag))

    ax[preamble_idx][2].set_ylabel("Count")
    ax[preamble_idx][2].hist(margins, bins=30, color="black", edgecolor="black", alpha=0.7)

    ax[preamble_idx][3].hist(peak_diffs, bins=30, color="black", edgecolor="black", alpha=0.7)

ax[0][0].set_title("Received I/Q samples")
ax[0][1].set_title("Correlation snapshot")
ax[0][2].set_title("Margin distribution")
ax[0][3].set_title("Peak spacing differences")
ax[3][0].set_xlabel("Sample index")
ax[3][1].set_xlabel("Sample index")
ax[3][2].set_xlabel("Margin Bins (peak/threshold)")
ax[3][3].set_xlabel("Peak Spacing difference (samples)")

fig.tight_layout()
plt.savefig(f"figures/preamble_ota_capture_{SILENCE_LEN}.png", dpi=300)

plt.show()