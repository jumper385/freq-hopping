# Frozen PlutoSDR Results Analysis — 2026-05-10

This analysis uses only the frozen CSV files from the 2026-05-10 PlutoSDR bring-up checkpoint. No additional SDR experiments were run.

## Generated plots

- `docs/plots/retune_timing.png`
- `docs/plots/ser_distribution.png`
- `docs/plots/live_ucb_loop.png`
- `docs/plots/mab_sim_regret.png`

## Key quantitative summaries

- RX retune: min 2.58 ms, mean 3.95 ms, median 3.99 ms, max 4.21 ms
- TX retune: min 2.47 ms, mean 3.88 ms, median 3.93 ms, max 4.11 ms
- RX retune + capture: min 12.76 ms, mean 16.65 ms, median 16.38 ms, max 28.24 ms
- Fixed 915 MHz link, -60 dB TX: SER min 0.00%, mean 9.98%, median 2.91%, max 76.28%
- Fixed 915 MHz link, -50 dB TX: SER min 0.00%, mean 2.53%, median 2.56%, max 6.51%
- Fixed 915 MHz link, -50 dB TX, no abnormal peak-count outlier: SER min 0.00%, mean 2.53%, median 2.56%, max 6.51%
- FH loop 914/915/916 MHz, -50 dB TX: SER min 0.00%, mean 1.84%, median 0.58%, max 6.28%
- FH loop 914/915/916 MHz, -50 dB TX, normal peak count: SER min 0.00%, mean 1.84%, median 0.58%, max 6.28%
- FH loop 914/915/916 MHz, -50 dB TX: sequential TX+RX retune min 6.90 ms, mean 7.98 ms, median 8.06 ms, max 8.37 ms
- Live UCB hardware loop: SER min 0.00%, mean 6.41%, median 2.56%, max 76.28%
- Live UCB hardware loop, normal peak count: SER min 0.00%, mean 2.30%, median 2.33%, max 6.28%
- Live UCB hardware loop: reward min 0.24, mean 0.94, median 0.97, max 1.00
- Live UCB hardware loop: peak margin min 2.19×, mean 2.72×, median 2.83×, max 3.09×

## Interpretation

1. **The basic PlutoSDR OFDM/QPSK link is working.** The clean fixed-link -50 dB run stayed between 0% and 6.51% SER over 10 bursts, substantially better than the -60 dB run, which had a 76.28% acquisition/timing outlier.
2. **Frequency hopping works at the bring-up level.** The -50 dB three-channel hop loop achieved 1.84% mean SER over 12 hops with no severe outlier, while sequential TX+RX retuning averaged about 7.98 ms.
3. **The first hardware-in-the-loop MAB path is functional.** UCB selected channels, retuned both radios, demodulated bursts, converted SER to reward, and updated online. The 18-hop run had 6.41% mean SER including one clear timing/acquisition outlier; excluding abnormal peak-count cases gives a representative SER near the low-single-digit range.
4. **Acquisition confidence needs to become part of the reward gate.** Outliers correlate with abnormal preamble peak counts (e.g. 64 peaks), so packet validity should be separated from channel quality before comparing algorithms.
5. **The ≤2 ms retune claim is not supported by the measured host-control path.** Single-radio retunes were about 3.9 ms mean; sequential TX+RX retunes were about 8 ms mean. This should be framed as a measured timing budget, not a failure of the thesis.

## Claim coverage impact

- **C5 (OFDM/QPSK suitability): strengthened but not complete.** Frozen data supports feasibility of OFDM/QPSK at 915 MHz; controlled BLER/PER and interference tests are still needed.
- **C7 (PlutoSDR can support useful MAB-FH): strengthened.** Both fixed-link and hopping runs worked on two Plutos. Useful hop rate must be bounded by measured retune/capture/acquisition timing.
- **C10 (MAB-FH beats static/random): not yet covered by hardware.** Only UCB was run live. Need side-by-side frozen-protocol trials with static/random/UCB/TS/EXP3 and a controlled interferer.
- **C13/C14/C15 (BLER/throughput targets): still uncovered.** Current SER proxy is useful for bring-up but is not packet BLER or throughput.
- **C18/C27/C30 (preamble/acquisition pipeline): strengthened.** ZC/OFDM acquisition works often enough for bring-up, but abnormal peak counts show packet-validity gating is necessary.
- **C19 (≤2 ms retune): contradicted for current implementation.** This should remain BLOCKED unless the architecture changes or lower-level tuning proves faster.
- **C21 (MAB computation negligible): partly implied but not directly measured.** Demod/capture/retune dominate logs; add explicit agent decision timing later.

## Recommended progress-update wording

> A first PlutoSDR hardware bring-up was completed using two networked ADALM-Pluto units. The OFDM/QPSK link was validated at 915 MHz, followed by a three-channel frequency-hopping loop over 914/915/916 MHz. At -50 dB TX attenuation the fixed-link run achieved 2.54% mean SER, while the three-channel hop loop achieved 1.84% mean SER over 12 hops. A first live UCB multi-armed-bandit control loop was also demonstrated, using measured SER as a bounded reward (`1 - SER`). The main risk identified is timing/acquisition robustness: host-controlled retuning averaged about 3.9 ms per radio and about 8 ms for sequential TX+RX retunes, contradicting the earlier ≤2 ms assumption and motivating packet-validity gating before algorithm comparison.

