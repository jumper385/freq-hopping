# Prototype Results — 2026-05-10 PlutoSDR Bring-Up

## Setup

- RX PlutoSDR: `ip:192.168.8.93`
- TX PlutoSDR: `ip:192.168.8.94`
- Test band: 914–916 MHz
- Sample rate: 1 MSPS
- OFDM/QPSK burst modem from `src/OFDM.py`
- TX attenuation/gain tests: `-60 dB`, then `-50 dB`
- Logs saved under `results/` locally; generated logs are ignored by git.

## Device Discovery

Both PlutoSDRs were reachable over libiio after installing system `libiio0`.

## Retune Timing

### RX-only retune benchmark

Command:

```bash
python scripts/retune_benchmark.py --uri ip:192.168.8.93 --freq 914000000 915000000 916000000 --loops 30 --capture --out results/rx_retune_benchmark.csv
```

Result:

- Retune only: min 2.58 ms, mean 3.95 ms, max 4.21 ms
- Retune + one RX capture: min 12.76 ms, mean 16.65 ms, max 28.24 ms

### TX-only retune benchmark

Command:

```bash
python scripts/retune_benchmark.py --uri ip:192.168.8.94 --freq 914000000 915000000 916000000 --loops 30 --out results/tx_retune_benchmark.csv
```

Result:

- Retune only: min 2.47 ms, mean 3.88 ms, max 4.11 ms

### Paired hop-loop retune timing

Command:

```bash
python scripts/fh_loop.py --tx-uri ip:192.168.8.94 --rx-uri ip:192.168.8.93 --freqs 914000000,915000000,916000000 --tx-gain -60 --hops 9 --settle-ms 5 --out results/fh_loop_914_916mhz.csv
```

Result:

- Retuning both TX and RX sequentially: min 6.40 ms, mean 7.95 ms, max 8.42 ms
- Capture time: mean 89.43 ms
- Demodulation time: mean 1.84 ms

Interpretation: the earlier proposal assumption of ≤2 ms retuning is too optimistic for the current Python/libiio host-control path. A safe early hop budget should assume several milliseconds per radio, plus capture/acquisition time.

## Fixed-Link Smoke Test

### 915 MHz, TX gain -60 dB

Command:

```bash
python scripts/link_smoke.py --tx-uri ip:192.168.8.94 --rx-uri ip:192.168.8.93 --freq 915000000 --tx-gain -60 --bursts 10 --out results/link_smoke_915mhz.csv
```

Result:

- SER mean: 9.98%
- SER min: 0.00%
- SER max: 76.28%
- Preamble peaks: usually 31–32, one outlier at 64 peaks

Interpretation: link works, but low TX power produced occasional detection/timing failures.

### 915 MHz, TX gain -50 dB

Command:

```bash
python scripts/link_smoke.py --tx-uri ip:192.168.8.94 --rx-uri ip:192.168.8.93 --freq 915000000 --tx-gain -50 --bursts 10 --out results/link_smoke_915mhz_txm50.csv
```

Result:

- SER mean: 2.54%
- SER min: 0.00%
- SER max: 6.51%
- Preamble peaks: stable at 31–32 peaks

Interpretation: increasing TX level by 10 dB substantially improved stability without changing the receiver algorithm. Next work should separate link-margin effects from preamble/timing ambiguity.

## Thesis Impact

- Supports PlutoSDR OTA OFDM/QPSK feasibility at 915 MHz.
- Weakens/refutes the specific ≤2 ms retune assumption for the current host-controlled Python/libiio implementation.
- Provides the first concrete hop timing budget for the proposal.
- Shows that receiver acquisition and cyclic-buffer timing ambiguity are now practical engineering risks worth measuring explicitly.

## Next Tests

1. Add per-burst correlation peak margin and chosen P1/P2 indices to logs.
2. Sweep TX attenuation and RX gain to map SER vs link margin.
3. Measure retune timing with TX/RX retunes overlapped or minimised, if architecture permits.
4. Add ACK/PER-style reward logging so the MAB agent can use real hardware rewards.
