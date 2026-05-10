# Close-Range Antenna OTA Results Analysis — 2026-05-10

This analysis uses the new close-range antenna dataset collected after replacing the coax connection with two nearby antennas. The coax dataset remains the controlled bench baseline; the OTA dataset tests the same code path with a real radiated link.

## Plots

- `docs/plots/coax_vs_ota_ser.png`
- `docs/plots/coax_vs_ota_preamble_peaks.png`
- `docs/plots/ota_live_ucb_loop.png`

## Summary statistics

- Coax link -50: SER min 0.00%, mean 2.53%, median 2.56%, max 6.51%; peaks min 31.00, mean 31.90, median 32.00, max 32.00
- OTA link -60: SER min 70.00%, mean 75.56%, median 75.93%, max 78.60%; peaks min 0.00, mean 0.90, median 0.50, max 3.00
- OTA link -50: SER min 72.33%, mean 75.12%, median 75.35%, max 78.84%; peaks min 0.00, mean 0.92, median 1.00, max 2.00
- OTA link -40: SER min 71.63%, mean 74.75%, median 74.77%, max 76.98%; peaks min 0.00, mean 0.75, median 1.00, max 2.00
- Coax FH -50: SER min 0.00%, mean 1.84%, median 0.58%, max 6.28%; peaks min 30.00, mean 31.67, median 32.00, max 32.00
- OTA FH -40: SER min 70.00%, mean 74.73%, median 74.88%, max 76.74%; peaks min 0.00, mean 0.75, median 1.00, max 2.00
- OTA UCB -40: SER min 71.16%, mean 75.04%, median 75.58%, max 78.60%; peaks min 0.00, mean 0.94, median 0.50, max 4.00

## Interpretation

1. The close-range antenna link did not acquire reliably at -60, -50, or -40 dB TX attenuation. SER stayed around 70–80%, close to an effectively failed QPSK demodulation, and detected preamble peaks were near 0–3 rather than the ~32 peak pattern seen in the coax runs.
2. Increasing TX level from -60 to -40 dB did not materially improve acquisition. That suggests the current problem may not be simple link margin alone; antenna mismatch/orientation, RX gain, saturation, cabling removal changing amplitude assumptions, thresholding, or frame timing logic may be involved.
3. The live UCB loop still executed as a control loop, but its rewards were not meaningful channel-quality rewards. Mean reward was about 0.25 because SER was high on all channels. In this condition the agent cannot learn useful frequency preference; it is mostly observing receiver failure.
4. This is useful thesis evidence because it separates two milestones: coax validated the digital SDR/control path, while OTA now exposes the next real RF/acquisition problem that must be solved before anti-jamming experiments are credible.

## Claim impact

- C5 / OFDM-QPSK suitability: coax evidence remains positive, but OTA evidence weakens any broad claim that the current receiver is already robust. Keep this as partially-supported only.
- C7 / PlutoSDR MAB-FH feasibility: control-path feasibility remains supported, but OTA link feasibility is not yet demonstrated with the current antenna setup.
- C18/C27/C30 / acquisition pipeline: the OTA dataset challenges the current ZC threshold/acquisition implementation. Packet-validity gating and acquisition debugging are now immediate blockers.
- C10 / MAB beats baselines: still not tested. OTA data is not suitable for algorithm comparison because all channels are failing similarly.
- C19 / retune timing: unchanged; retune timing remains around 8 ms sequential TX+RX.
