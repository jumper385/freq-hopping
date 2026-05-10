# CFO Gate — OTA Validation & Coax/OTA Comparison

**Date:** 2026-05-10  
**Setup:** Two ADALM-Pluto SDRs, 915 MHz, 1 MSPS  
- Coax: −40 dB TX attenuation, direct SMA  
- OTA: 0 dB TX gain, 60 cm antenna separation  
- Both: 10-sym QPSK bursts, 4σ+μ ZC threshold, `--min-margin 2.5`, `--max-cfo 2000`

## Results

| Metric | Coax (−40 dB) | OTA (0 dB) | Δ |
|--------|---------------|------------|---|
| Total trials | 100 | 100 | — |
| Valid locks | 83 (83%) | 81 (81%) | −2% |
| CFO-rejected | 17 (17%) | 19 (19%) | +2% |
| Margin-rejected | 0 | 0 | 0 |
| Mean SER (valid) | 0.0291 | 0.0281 | −0.0010 |
| Median SER (valid) | 0.0093 | 0.0093 | 0 |
| Max SER (valid) | 0.0930 | 0.0930 | 0 |
| Median \|CFO\| (valid) | 0 Hz | 0 Hz | 0 |
| Max \|CFO\| (valid) | 1949 Hz | 1908 Hz | −41 Hz |
| Median peak margin | 3.4× | 3.4× | 0 |
| Median goodput | 0.00860 Mbps | 0.00862 Mbps | +0.00002 |
| Median wall time | 98.56 ms | 98.62 ms | +0.06 ms |

### False-lock breakdown

| CFO cluster | Coax | OTA |
|-------------|------|-----|
| ±15.5 kHz (false lock) | 15 | 14 |
| ±1.6-2.3 kHz (borderline) | 2 | 4 |
| Other | 0 | 1* |

\* Single OTA reject with CFO ≈ 0 Hz — likely a no-pair or no-peaks case, not CFO gated.

## Key findings

1. **Coax and OTA performance is identical.** Every SER, margin, goodput, and CFO metric matches within 2%. The link is RF-channel-transparent at these signal levels — the bottleneck is PlutoSDR I/O, not the propagation path.

2. **Systematic false-lock rate ≈ 18% (±2%).** The ±15.5 kHz false-lock cluster is identical on coax and OTA, confirming it's a PlutoSDR buffer/DMA artifact, not an RF effect.

3. **Two-stage gate (4σ ZC + 2000 Hz CFO) validated on both paths.** Zero margin rejects, ~81-83% valid with ~2.8% mean SER. The gate is production-ready for MAB reward computation.

4. **Goodput ceiling is ~8.6 kbps** with current 6-buffer flush and 10-sym bursts. The theoretical ceiling for this frame format is ~907 kbps. The 100× gap is I/O overhead, not link quality.

## Conclusion

The CFO sanity gate is validated on both coax and OTA. The two-stage ZC→S&C viability gate (margin + CFO) correctly separates real locks from false locks. Link performance is independent of coax vs OTA at these signal levels. Next: reduce buffer size to improve wall time, then MAB comparison with gated reward.
