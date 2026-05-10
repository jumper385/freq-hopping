# Buffer Size 4096 Benchmark — CFO Gate Result

**Date:** 2026-05-10  
**Command:** `python scripts/throughput_benchmark.py --tx-uri ip:192.168.8.94 --rx-uri ip:192.168.8.93 --freq 915e6 --tx-gain 0 --per-config 100 --min-margin 2.5 --max-cfo 2000 --buffer-size 4096`  
**Output CSV:** `results/throughput_benchmark.csv`

## Summary

| Metric | Value |
|---|---:|
| Total trials | 100 |
| Valid locks | 76/100 (76.0%) |
| Invalid locks | 24/100 (24.0%) |
| Mean SER (valid) | 0.0233 |
| Median SER (valid) | 0.00465 |
| Max SER (valid) | 0.0907 |
| Median wall time | 24.59 ms |
| Median goodput | 0.03480 Mbit/s |

## Invalid breakdown

- 20 CFO outliers near ±15.5 kHz / one at 2.8 kHz / one at 2.09 kHz
- 2 no-valid-pair cases (`no valid P1/P2 pair (12 peaks)`)
- 2 low-margin cases (`~2.48 < 2.5`)

## Interpretation

Reducing RX buffer size from 16,384 to 4,096 **did not reduce false-lock rate**; valid-lock rate fell to 76%. However, it reduced wall time from ~98 ms to ~24.6 ms and raised effective goodput from ~8.6 kbps to ~34.8 kbps. This means buffer size is a throughput/latency knob, not the main false-lock fix.

The +15.5 kHz false-lock cluster persists in repeated blocks, indicating the receiver is selecting the first plausible P1/P2 pair in a buffer that contains multiple candidate pairs. Next fix should not be another scalar threshold; it should evaluate multiple candidate preamble pairs and choose the best lock.

## Next design direction

Implement multi-candidate acquisition:

1. Return all adjacent P1/P2 pairs spaced 32±2 samples, not only the first pair.
2. For each candidate pair:
   - compute CFO and reject if outside gate,
   - compute peak margin and P1/P2 amplitude consistency,
   - optionally demodulate pilots/payload and score EVM/SER proxy.
3. Choose the best candidate instead of rejecting the burst because the first candidate is false.
4. Pass the selected acquisition metadata into `demodulate_burst` so demodulation uses the same candidate as acquisition.

This should convert many current CFO-rejected bursts into valid locks and is the most direct path toward 95%+ baseline comms performance.
