# Baseband Communication System Review — 2026-05-10

## Scope

Offline/code-level review of the current OFDM/QPSK baseband path in `src/OFDM.py`, plus new tests for theoretical payload throughput and clean/impaired burst round-trip behaviour. This does **not** include PlutoSDR hardware, retune latency, stale-buffer flushing, packet erasures, FEC, or jammer effects.

## Current Frame Format

Default `OFDM(n_tones=50, cp_len=16, roll_off=0)`:

- FFT bins: `n_tones + 16 guards = 66`
- Active tones: `50`
- Pilot tones: every 8th active tone → `7`
- Payload tones: `43`
- QPSK payload per OFDM symbol: `86 bits`
- Per-symbol block: `66 FFT + 16 CP + roll_off`
- Burst overhead: `32 silence + 32 ZC + 32 ZC + 32 silence = 128 samples`

At `1 MSPS`, ideal framing-only QPSK throughput is:

- Single-symbol frame, `roll_off=0`: `0.410 Mbit/s`
- 10-symbol burst, `roll_off=0`: `0.907 Mbit/s`
- 10-symbol burst, `roll_off=8`: `0.837 Mbit/s`
- 10-symbol burst, `n_tones=100`, `cp_len=16`, `roll_off=0`: `1.202 Mbit/s`

These are upper bounds for valid decoded payload bits. Real measured application throughput will be lower once capture latency, demod time, retunes, invalid packets, guard waits, and any retransmission/FEC are included.

## New Test Coverage

Added `tests/test_ofdm_throughput.py`:

- Verifies frame/sample accounting for FFT length, payload tones, CP, roll-off, sync overhead, and burst length.
- Verifies theoretical QPSK throughput calculations.
- Verifies bursting amortises preamble/silence overhead: 10-symbol burst is >2× the single-symbol framing throughput for current defaults.
- Verifies roll-off windowing has an explicit throughput cost.
- Verifies clean full-payload burst round-trip.
- Verifies burst round-trip with CFO + AWGN remains decodable in a moderate impairment case.
- Compares optimisation scenarios: larger active grid and burst framing are bigger wins than tiny CP tweaks.

Current test gate:

```text
71 passed in 0.24s
```

## Engineering Read

### What is actually solid

- The pure NumPy baseband path is now testable and deterministic.
- The modem supports a useful burst mode, which is absolutely the right direction. Single-symbol frames waste too much on silence/preamble overhead.
- The pilot/equalizer chain is simple enough to debug and reason about.
- CFO correction is reasonable for the current dual-preamble design, provided the actual Pluto CFO sits inside the estimator's unambiguous range.
- The new throughput helpers make the framing tradeoffs explicit instead of buried in comments/scripts.

### What is jerryrigged / fragile

1. **No explicit packet validity result.**
   `demodulate_burst()` returns symbols even if timing acquisition is weak or false. Scripts then compute SER regardless. This is dangerous for MAB rewards because bad acquisition becomes a noisy reward instead of a rejected packet.

2. **Preamble detection threshold is heuristic.**
   `mean + 5σ` works in clean buffers but is not a calibrated detector. OTA failure showed the peak-count metric collapses. We need a proper acquisition confidence output: peak margin, P1/P2 spacing, correlation max/threshold, and maybe normalized correlation.

3. **Payload has no packet header / sequence / CRC.**
   The receiver only knows the payload because the script generated the same random payload locally. That is fine for smoke tests, but not a real link. A hardware trial should log packet validity via CRC/PER, not just symbol decisions against a known array.

4. **SER reward is unsafe without validity gating.**
   `reward = 1 - SER` is okay only after confirming a valid packet lock. OTA runs with weak/absent preamble peaks should produce `valid=False, reward=0`, not a misleading SER-like value from random demod output.

5. **CFO range is tight for worst-case Pluto tolerance.**
   32-sample repeated preamble gives ±15.625 kHz at 1 MSPS. Two Plutos at 915 MHz and ±20 ppm can differ by ~18.3 kHz worst-case. In practice it may work, but the stated margin is not guaranteed. Longer repeated preambles reduce range; shorter increase range but reduce estimator quality. A two-stage estimator or known-frequency calibration would be better.

6. **FFT size / subcarrier layout is odd.**
   `n_tones + 16 = 66` by default, which is not a power of two. NumPy handles it, but SDR/OFDM conventionally benefits from power-of-two FFT sizes and clearer bin semantics. This is okay for prototype code, but not ideal for a clean thesis modem.

7. **Guard bands double as noise estimator.**
   Estimating noise from guard bins is convenient, but in SDR hardware guard-bin energy also contains leakage, DC/IQ artefacts, timing error, and adjacent-channel garbage. Useful diagnostic, not a perfect noise variance.

8. **Scripts duplicate payload-tone logic.**
   Several scripts rebuild the pilot mask manually. New `data_tone_count` should replace that so scripts cannot drift from the modem.

9. **`main.py` radio variable naming looks suspicious.**
   It creates `rx_sdr = PlutoSDR(uri="usb:", tx_gain=-20)` and `tx_sdr = PlutoSDR(uri="ip:192.168.8.93", rx_gain=30)`. That may just be naming/comment rot, but it is easy to operate the wrong radio.

## Optimisation Priorities

Recommended order:

1. **Add validity-gated demod metadata.**
   Return or expose: `valid`, `p1`, `p2`, `peak_count`, `peak_margin`, `frame_start`, `cfo_norm`, and error reason. Make MAB reward depend on valid lock.

2. **Use burst mode aggressively.**
   For current defaults at 1 MSPS, going from 1 to 10 OFDM symbols improves ideal QPSK throughput from `0.410` to `0.907 Mbit/s`. This is the biggest easy win.

3. **Move to a cleaner FFT/grid.**
   Consider `fft_len=64` or `128` as the primary parameter, then define guard/pilot/data bins inside it. Current default `66` is awkward.

4. **Add packet header + CRC.**
   Even a tiny header with packet ID, payload length, and CRC16/CRC32 would make PER/throughput real instead of inferred.

5. **Separate modem metrics from hardware metrics.**
   Baseband theoretical throughput, demod CPU time, SDR capture time, retune time, valid packet rate, and application goodput should be logged separately.

6. **Debug OTA acquisition before more bandit trials.**
   Until ZC peaks and packet validity recover over antennas, MAB performance measurements are not meaningful.

## Suggested Next Code Step

Refactor `OFDM.demodulate_burst()` internally around a small acquisition helper, e.g.:

```python
@dataclass
class AcquisitionResult:
    valid: bool
    frame_start: int | None
    p1: int | None
    p2: int | None
    peak_count: int
    peak_margin: float
    cfo_norm: float
    reason: str
```

Then scripts can reject invalid packets before computing SER/reward. That will make the hardware experiments much cleaner and stop the RL loop from learning from garbage packets.
