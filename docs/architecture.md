# System Architecture

## Overview

This project generates OFDM (Orthogonal Frequency-Division Multiplexing) waveforms and transmits them over the air using an Analog Devices ADALM-PLUTO (PlutoSDR) software-defined radio. The design separates waveform generation from radio hardware control so each concern can be developed and tested independently.

```
┌─────────────────────────────────────────────────┐
│                    main.py                       │
│  orchestrates waveform generation + SDR I/O      │
└────────────┬──────────────────┬─────────────────┘
             │                  │
             ▼                  ▼
  ┌──────────────────┐  ┌───────────────────────┐
  │    src/OFDM.py   │  │   src/OFDMModulator.py│
  │  (primary modem) │  │ (alternate modulator) │
  └──────────────────┘  └───────────────────────┘
             │
             ▼
  ┌──────────────────┐
  │  src/PlutoSDR.py │
  │  (radio wrapper) │
  └──────────────────┘
             │
             ▼
     [ PlutoSDR Hardware ]
        USB / Ethernet
```

---

## Components

### `src/OFDM.py` — Primary OFDM Modem

The `OFDM` class is the main waveform engine. It handles the full modulate/demodulate pipeline and is designed to produce frames ready for over-the-air transmission.

**Key responsibilities:**
- Subcarrier mapping: places data symbols and pilots onto the OFDM subcarrier grid.
- Guard bands: 8-bin DC and high-frequency guards flank the active region.
- Pilot insertion: pilots at every 8th active subcarrier, fixed value `1+1j`, used for channel estimation and equalization on receive.
- Preamble generation: produces a Zadoff-Chu (ZC) sequence for frame sync and CFO estimation.
- Frame assembly: `[silence(32)] [ZC preamble(32)] [ZC preamble(32)] [OFDM symbol] [silence(32)]`.
- IFFT / FFT: converts between frequency and time domain.
- CFO correction: Schmidl-Cox estimator — measures the phase of the conjugate product of the two received preamble windows (`φ = ∠Σ r₂·r₁*`) to compute the fractional CFO in cycles/sample, then counter-rotates the whole buffer. Unambiguous range: ±f_s/(2N) = ±15 625 Hz at 1 MSPS, covering the ±20 ppm LO mismatch of two independent PlutoSDRs at 915 MHz.
- Frame timing: anchors on the **second** detected preamble peak (P2); data starts one preamble-length (32 samples) after P2. This is more robust than P1+64 when the leading silence suppresses P1's correlation peak.
- Channel estimation: LS pilot extraction + linear interpolation across all subcarriers.
- Zero-forcing equalization: per-subcarrier division by the estimated channel response.
- Residual phase correction: after ZF equalization, computes the mean pilot phase deviation from the expected `1+1j` and counter-rotates all subcarriers. Removes common-phase error from LO phase noise or imperfect CFO correction.

**Subcarrier layout** (for `n_tones` active bins, default 100):

```
Bin index:  0        7  8             8+n_tones-1  8+n_tones  ...  n_tones+15
            [guard(8)] [data + pilots (n_tones)]  [guard(8)]
```

**Frame layout** (in samples):

```
| silence 32 | preamble 32 | preamble 32 | OFDM symbol (n_tones+16) | silence 32 |
```

---

### `src/OFDMModulator.py` — Alternate Modulator

`OFDMModulator` is a standalone modulator that provides a slightly different subcarrier layout: data starts at bin 100 and pilots are placed at configurable fixed bins across the spectrum. It appends a configurable-length cyclic prefix and scales the output to 16-bit integer range.

It does **not** include a preamble or synchronisation mechanism; it is best suited for channel-impairment testing or back-to-back loopback scenarios.

**Key differences from `OFDM`:**

| Feature | `OFDM` | `OFDMModulator` |
|---|---|---|
| Preamble | ZC sequence (×2) | None |
| Cyclic prefix | Not added in `modulate()` | Yes (`cp_len`, default 128) |
| Pilot placement | Every 8th active bin | Configurable list of absolute bins |
| CFO correction | Yes (dual-preamble) | No |
| Output scaling | Normalised to ±1 | Scaled to `2^14` (16-bit) |

---

### `src/PlutoSDR.py` — Radio Hardware Wrapper

`PlutoSDR` wraps the `pyadi-iio` `adi.Pluto` driver and exposes a minimal TX/RX interface.

**Responsibilities:**
- Configures the Pluto at construction time: sample rate, RF bandwidth, LO frequency, TX/RX gain, buffer size, and cyclic TX mode.
- `transmit(iq)`: normalises the IQ array to ±1, scales to 16-bit range (`2^14`), and calls `sdr.tx()`. The cyclic buffer flag causes the Pluto to loop the waveform continuously until `stop_transmit()` is called.
- `stop_transmit()`: destroys the TX buffer to halt continuous transmission.
- `receive()`: flushes 5 stale buffers before capturing one clean buffer, then normalises to ±1.

**Default radio parameters:**

| Parameter | Default |
|---|---|
| Center frequency | 915 MHz |
| Sample rate | 1 MSPS |
| TX gain | −20 dB |
| RX gain | 30 dB |
| Buffer size | 16 384 samples |

---

### `main.py` — Entry Point

Wires the components together for a full TX → RX loopback test:

1. Instantiates `OFDM` and two `PlutoSDR` instances (TX and RX, both pointing at the same IP in the current config).
2. Builds a small test payload (4 complex symbols) and modulates it into a frame.
3. Transmits the frame continuously via the TX radio.
4. Captures a buffer from the RX radio.
5. Stops transmission and plots the received I/Q waveform.
6. Demodulates the received buffer and prints the first 4 recovered symbols.

---

## Data Flow

```
symbols (complex ndarray)
        │
        ▼
  OFDM.modulate()
   ├─ _construct_iframe()   ← pilots + guard bands
   ├─ _ifft()               ← freq → time domain
   ├─ normalise amplitude
   └─ prepend preambles + silence
        │
        ▼ time-domain frame (complex64)
        │
  PlutoSDR.transmit()
   ├─ normalise to ±1
   └─ scale to int16 (×2^14) → sdr.tx()
        │
        ▼  RF over the air (915 MHz, 1 MSPS)
        │
  PlutoSDR.receive()
   ├─ flush stale buffers
   └─ sdr.rx() → normalise ÷ 2^14
        │
        ▼ received frame (complex64)
        │
  OFDM.demodulate()
   ├─ _cancel_cfo()             ← Schmidl-Cox CFO estimate + de-rotation
   │    φ = ∠Σ(r₂·r₁*)  →  f_cfo = φ/(2π·32)
   ├─ _preamble_detect()        ← ZC cross-correlation, threshold = μ+5σ
   ├─ timing anchor on P2       ← data_start = peaks[1] + 32
   ├─ FFT
   ├─ _estimate_channel()       ← LS at pilots, linear interp across all bins
   ├─ _equalize()               ← zero-forcing: X̂[k] = Y[k]/H[k]
   ├─ _correct_residual_phase() ← mean pilot phase error → counter-rotate
   └─ strip pilots + guard bins
        │
        ▼
  recovered symbols (complex ndarray)
```

---

## Receiver Signal Chain (Cross-SDR Detail)

When TX and RX are **different physical PlutoSDRs**, each has an independent crystal oscillator. At 915 MHz with ±20 ppm tolerance the LO mismatch can reach ±18 300 Hz. The three-stage synchronisation pipeline handles this:

```
Received samples (complex64, ±1 normalised)
        │
        ▼  Stage 1 — Coarse CFO correction
  _cancel_cfo()
   • Locate both preamble peaks via ZC cross-correlation.
   • Compute Schmidl-Cox estimate from the two received preamble windows:
       φ  = ∠ Σ( r₂[k] · r₁*[k] )      (sum over k = 0…N-1, N=32)
       f_cfo = φ / (2π · N)              (cycles/sample)
   • Counter-rotate entire buffer: y_corr[n] = y[n] · exp(-j 2π f_cfo n)
   • Unambiguous range: ±f_s/(2N) = ±15 625 Hz @ 1 MSPS
        │
        ▼  Stage 2 — Frame timing
  _preamble_detect()  (on the CFO-corrected buffer)
   • Cross-correlate with the known 32-sample ZC sequence.
   • Threshold: μ + 5σ of the correlation magnitude.
   • Anchor on second peak (P2): data_start = peaks[1] + 32
     (P2 anchor is robust against P1 being suppressed by the
      leading silence or a buffer boundary.)
        │
        ▼  Strip + FFT
  y_stripped = y_corr[data_start : data_start + n_tones + 16]
  Y = FFT(y_stripped)
        │
        ▼  Stage 3 — Channel equalisation + residual phase
  _estimate_channel(Y)
   • LS at each pilot bin: H[k] = Y[k] / (1+1j)
   • Linear interp (real & imag separately) across all bins.
  _equalize(Y, H)
   • Zero-forcing: X̂[k] = Y[k] / H[k]
  _correct_residual_phase(X̂)
   • After ZF, pilots should equal 1+1j.  Any common rotation
     (residual CFO phase, LO phase noise, TA error) appears as a
     shared angle offset across all pilots:
       θ_err = mean( ∠( X̂[pilot_k] / (1+1j) ) )
   • Counter-rotate: X̂_corr[k] = X̂[k] · exp(-j θ_err)
        │
        ▼
  Extract data subcarriers (strip guard bands and pilots)
        │
        ▼
  Recovered symbols (complex ndarray)
```

**Why each stage matters for cross-SDR:**

| Stage | Problem addressed | Magnitude at 915 MHz / 1 MSPS |
|---|---|---|
| Schmidl-Cox CFO | LO frequency mismatch between TX and RX crystals | Up to ±18 300 Hz (±20 ppm) |
| P2 timing anchor | P1 correlation peak suppressed by buffer edge or silence | Up to ±1 symbol (116 samples) |
| Residual phase correction | Phase accumulated across the OFDM symbol after coarse CFO removal; LO phase noise | Typically < 10° but enough to rotate constellation points |

---

## Dependencies

| Library | Purpose |
|---|---|
| `numpy` | Array math, FFT/IFFT |
| `matplotlib` | Waveform / constellation plotting |
| `pyadi-iio` (`adi`) | PlutoSDR hardware driver |
