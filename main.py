import numpy as np
import matplotlib.pyplot as plt

from src.OFDM import OFDM
from src.PlutoSDR import PlutoSDR

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# cp_len  : cyclic prefix in samples.  At 1 MSPS this is 16 µs — covers most
#           indoor multipath delay spreads.  Increase if you see ISI.
# roll_off: raised-cosine window edge length.  8 samples gives a clean spectral
#           skirt with minimal OOB leakage.  Set to 0 to disable.
# N_SYMS  : OFDM symbols per burst.  Each symbol carries DATA_TONES data tones.
CP_LEN   = 16
ROLL_OFF = 8
N_SYMS   = 10

def main():
    ofdm = OFDM(cp_len=CP_LEN, roll_off=ROLL_OFF)

    # Number of data tones per symbol (pilots excluded)
    pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
    pilot_mask[::8] = True
    data_tones = int(np.count_nonzero(~pilot_mask))

    # two radios: USB-attached TX, IP-attached RX
    rx_sdr = PlutoSDR(uri="usb:", tx_gain=-20)
    tx_sdr = PlutoSDR(uri="ip:192.168.8.93", rx_gain=30)

    # build a multi-symbol burst payload
    rng = np.random.default_rng(64)
    symbols_matrix = (
        rng.choice([-1, 1], size=(N_SYMS, data_tones))
        + 1j * rng.choice([-1, 1], size=(N_SYMS, data_tones))
    ).astype(complex)

    burst = ofdm.modulate_burst(symbols_matrix)
    print(f"Burst: {N_SYMS} symbols × {data_tones} data tones — {len(burst)} samples total")

    print("Transmitting ...")
    tx_sdr.transmit(burst)

    print("Receiving ...")
    y = rx_sdr.receive()

    tx_sdr.stop_transmit()

    # --- CFO-correct the buffer once so debug plot matches what the detector sees ---
    y_cfo = ofdm._cancel_cfo(y)
    corr_mag, threshold = ofdm._correlate(y_cfo)
    peaks = ofdm._preamble_detect(y_cfo)
    pair  = ofdm._find_preamble_pair(peaks)

    print(f"\nPeak detection  threshold = {threshold:.4f}")
    print(f"  Rising-edge peaks ({len(peaks)} total): {peaks[:10]}{'...' if len(peaks) > 10 else ''}")
    if pair:
        print(f"  Valid P1/P2 pair: P1={pair[0]}  P2={pair[1]}  (spacing={pair[1]-pair[0]})")
        print(f"  → frame_start = {pair[1] + 32}")
    else:
        print("  WARNING: no valid P1/P2 pair found — timing fell back to heuristic")

    # --- recover all symbols from the burst ---
    recovered = ofdm.demodulate_burst(y, N_SYMS)

    # --- diagnostic plots ---
    fig, axes = plt.subplots(1, 3, figsize=(18, 4))

    axes[0].set_title("Received I/Q waveform")
    axes[0].plot(y.real, label="I")
    axes[0].plot(y.imag, label="Q")
    if pair:
        frame_start = pair[1] + 32
        axes[0].axvline(pair[0],    color="orange", linewidth=1.2, linestyle="--", label=f"P1 ({pair[0]})")
        axes[0].axvline(pair[1],    color="red",    linewidth=1.2, linestyle="--", label=f"P2 ({pair[1]})")
        axes[0].axvline(frame_start, color="lime",  linewidth=1.5, linestyle="-",  label=f"data start ({frame_start})")
        axes[0].plot(frame_start, y.real[frame_start], "v", color="lime", markersize=8)
    axes[0].legend(fontsize=7)
    axes[0].set_xlabel("Sample")

    axes[1].set_title("ZC correlation magnitude + threshold")
    axes[1].plot(corr_mag, linewidth=0.6, label="|corr|")
    axes[1].axhline(threshold, color="r", linewidth=1.0, linestyle="--",
                    label=f"threshold ({threshold:.3f})")
    for p in peaks:
        axes[1].axvline(p, color="g", linewidth=0.5, alpha=0.5)
    if pair:
        axes[1].axvline(pair[0], color="orange", linewidth=1.5, label=f"P1={pair[0]}")
        axes[1].axvline(pair[1], color="red",    linewidth=1.5, label=f"P2={pair[1]}")
    axes[1].legend(fontsize=7)
    axes[1].set_xlabel("Sample")

    axes[2].set_title(f"Equalized constellation ({N_SYMS} symbols)")
    flat = recovered.flatten()
    axes[2].scatter(flat.real, flat.imag, s=10, alpha=0.6)
    axes[2].axhline(0, color="k", linewidth=0.5)
    axes[2].axvline(0, color="k", linewidth=0.5)
    axes[2].set_xlabel("I")
    axes[2].set_ylabel("Q")
    axes[2].set_aspect("equal")

    plt.tight_layout()
    plt.show()

    print(f"\nRecovered symbols [{N_SYMS} × {data_tones}]:")
    for i, row in enumerate(recovered):
        print(f"  sym {i}: {row[:4]}  ...")

    # symbol error rate against known QPSK grid
    tx_flat = symbols_matrix.flatten()
    rx_flat = recovered.flatten()
    decisions = (np.sign(rx_flat.real) + 1j * np.sign(rx_flat.imag))
    tx_dec   = (np.sign(tx_flat.real) + 1j * np.sign(tx_flat.imag))
    ser = np.mean(decisions != tx_dec)
    print(f"\nSymbol error rate: {ser:.2%}  ({int(ser * len(tx_flat))}/{len(tx_flat)} errors)")


if __name__ == "__main__":
    main()
