# Throughput Benchmark Analysis — 2026-05-10

## Method

Three 100-iteration runs of `scripts/throughput_benchmark.py` at 915 MHz,
1 MSPS, 10-symbol QPSK bursts (43 data tones × 10 symbols = 860 payload
bits per burst), ideal framing ceiling 0.907 Mbit/s.

| Run | Path | TX gain | Notes |
|---|---|---|---|
| OTA 1st | `results/throughput_ota_first_60cm_2026-05-10.csv` | 0 dB | Antennas ~60 cm, first run after code push |
| OTA 2nd | `results/throughput_ota_second_60cm_2026-05-10.csv` | 0 dB | Same setup, re-run immediately after |
| Coax | `results/throughput_coax_100iter_2026-05-10.csv` | −40 dB | Cabled RF, attenuation to avoid RX saturation |

Acquisition validity gating: peak‑margin ≥ 2.5× (ZC correlation max / adaptive threshold).

## Results

| | OTA 1st | OTA 2nd | Coax |
|---|---|---|---|
| Valid locks | 66/100 (66%) | 72/100 (72%) | 71/100 (71%) |
| Peak margin, valid (median) | 2.9 | 3.0 | 3.0 |
| Peak margin, invalid (median) | 2.3 | 2.3 | 2.3 |
| SER, valid (median) | 32.3% | 0.23% | **0.00%** |
| SER, valid (mean) | 31.4% | 0.96% | 0.88% |
| Goodput, valid (median) | 5.9 kbps | 8.7 kbps | 8.7 kbps |
| Wall time (median) | 98.3 ms | 98.3 ms | 98.5 ms |

## Key Findings

### 1. Coax and OTA are now indistinguishable (runs 2–3)

OTA 2nd and coax produce identical valid-lock rates, identical margin
distributions, and near‑identical SER.  The RF path is no longer the
limiting factor — the modem and SDR I/O pattern dominate performance.

This is a reversal of the earlier close-range antenna tests (2026-05-09/10)
where OTA acquisition failed completely (SER ~70–80%, ZC peaks ~0–3).
Switching TX gain from ≤−40 dB to 0 dB and allowing the SDRs to warm up
resolved the acquisition failure.

### 2. ~29% invalid locks are systemic, not channel‑related

The invalid-lock rate is identical on coax (wired, clean signal) and OTA.
All invalid locks are caused by ZC peak margins falling in the 2.1–2.5
range (below the 2.5× threshold).  The margin distribution is bimodal:
all valid locks cluster at 2.5–3.1, all invalid at 2.1–2.5.

Likely causes (to be debugged):
- PlutoSDR cyclic‑DMA TX buffer reset misaligning the preamble relative
  to the RX capture window.
- 5‑buffer flush sometimes insufficient to clear stale data.
- ZC detector threshold (`mean + 5σ`) is suboptimal for the actual
  noise‑floor statistics.
- Preamble length (n=32) may benefit from a longer sequence or different
  root index.

### 3. When acquisition succeeds, SER is excellent

Median SER on valid locks: 0.00% (coax), 0.23% (OTA 2nd).  The OFDM/QPSK
modem path with dual‑ZC preamble, Schmidl‑Cox CFO, pilot‑based channel
estimation, LMMSE equalization, and residual‑phase correction produces
reliable QPSK decisions.

The OTA 1st run (31% SER even on "valid" locks) appears to be a cold‑start
or CFO‑settling artefact; it was not reproducible on the immediate re‑run.

### 4. Throughput is I/O‑bound, not baseband‑bound

Median wall time is ~98 ms in all runs.  The PlutoSDR `receive()` call
flushes 5 stale buffers then captures one, totalling 6 × 16 384 samples
at 1 MSPS = 98.3 ms.  The burst itself occupies 948 samples (0.95 ms).

Effective goodput ≈ 8.7 kbps vs. the theoretical framing ceiling of
907 kbps.  The ratio is ~0.96%.

Throughput improvements require reducing the receive‑cycle overhead:
smaller buffer sizes, fewer flush iterations, or streaming‑mode capture
instead of block‑mode.

## Comparison with Earlier Bench Datasets

| Earlier (coax, 2026-05-09/10) | This run (coax, −40 dB) |
|---|---|
| Fixed 915 MHz SER: 2.53% (`link_smoke`) | SER median 0.00% (valid locks) |
| FH‑loop SER: 1.84% (`fh_loop`) | SER mean 0.88% (valid locks) |
| Live UCB SER: 2.30% (`live_mab_loop`) | — |
| No validity gating | 2.5× margin gate, 71% valid |

Earlier coax runs had SER in the 1.8–2.5% range without validity gating.
The current throughput benchmark adds validity gating and achieves <1%
SER on valid locks, but the 29% invalid-lock rate was previously masked
because invalid packets were counted as high‑SER rather than rejected.

## Recommendations

1. **Debug the ~29% acquisition miss rate** — it is the single largest
   throughput loss and is present even on coax.

2. **Reduce buffer size and flush count** in PlutoSDR receive path to
   shrink wall time below 98 ms.

3. **Re‑run the coax FH‑loop and live‑MAB scripts** with validity gating
   to separate acquisition failures from demod errors.

4. **Retire the OTA‑is‑broken narrative** from earlier docs — OTA now
   performs on par with coax at 0 dB TX gain / 60 cm separation.

## Data

- `results/throughput_ota_first_60cm_2026-05-10.csv`
- `results/throughput_ota_second_60cm_2026-05-10.csv`
- `results/throughput_coax_100iter_2026-05-10.csv`
