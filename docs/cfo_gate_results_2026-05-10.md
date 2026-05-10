# CFO Sanity Gate — Validation Results

**Date:** 2026-05-10  
**Setup:** Two ADALM-Pluto SDRs, 915 MHz, 1 MSPS, coax at −40 dB, 10-sym QPSK bursts  
**Code:** `scripts/throughput_benchmark.py` with `--max-cfo 2000 --min-margin 2.5`

## Motivation

Threshold sweep from 5σ+μ to 4σ+μ boosted valid locks from ~71% to ~98% but inflated SER from <1% to ~25%. High-SER trials correlated perfectly with large Schmidl-Cox CFO estimates (±14-15 kHz vs ±0-500 Hz for real locks), identifying them as false locks. A CFO sanity gate was added to reject bursts with implausible CFO.

## Results

| Metric | Value |
|--------|-------|
| Total trials | 100 |
| Valid locks | 83/100 (83.0%) |
| CFO-rejected | 17/100 (17.0%) |
| Margin-rejected | 0/100 |
| Mean SER (valid) | 0.0291 |
| Median SER (valid) | 0.0093 |
| Max SER (valid) | 0.0930 |
| Median \|CFO\| (valid) | 0 Hz |
| Max \|CFO\| (valid) | 1949 Hz |
| Median peak margin | 3.4× |

### False-lock clusters

| Cluster | Count | Interpretation |
|---------|-------|---------------|
| ±15.5 kHz | 15 | Classic false locks — S&C CFO estimator on misaligned preamble data |
| ±2.0-2.3 kHz | 2 | Borderline; margins 3.0-3.1×, may be real high-CFO locks or false locks |

## Key findings

1. **All 17 rejects are CFO outliers.** The 4σ+μ threshold eliminates margin-based rejections entirely — every burst with a P1/P2 pair passes the ZC margin gate. The remaining invalids are exclusively false locks identified by implausible CFO.

2. **The CFO gate recovers both high lock rate AND low SER.** Stripping the 17% false locks drops mean SER from ~25% (before gate) to 2.9%. Median SER on valid locks is 0.93% — the real link quality.

3. **False locks are deterministic, not random.** The 15 false locks at ±15.5 kHz are tightly clustered (±100 Hz), ruling out random noise. They are a systematic artifact of the S&C CFO estimator operating on misaligned preamble samples — exactly the pattern predicted by the false-lock hypothesis.

4. **The 2 borderline cases (±2.0-2.3 kHz)** have decent margins (3.0-3.1×) and fall near the 2000 Hz gate. Their true lock status is ambiguous. A 3000 Hz gate would accept them; a 1000 Hz gate would reject them.

## Conclusion

The CFO sanity gate is validated on coax. It correctly rejects the systematic ±15.5 kHz false-lock cluster while preserving real locks with <3% mean SER. Recommend keeping `--max-cfo 2000` as default and verifying on OTA.
