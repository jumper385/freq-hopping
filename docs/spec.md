# Project Specification

## 1. Purpose

Generate OFDM baseband waveforms in software and transmit them over the air using an ADALM-PLUTO (PlutoSDR) software-defined radio. The system must support both standalone waveform generation (no hardware required) and live over-the-air TX/RX loopback testing.

---

## 2. Functional Requirements

### 2.1 OFDM Waveform Generator

| ID | Requirement |
|---|---|
| WG-01 | The system SHALL generate a baseband OFDM frame from an arbitrary array of complex input symbols. |
| WG-02 | The frame SHALL consist of a leading silence burst, two back-to-back Zadoff-Chu preambles, the OFDM data symbol, and a trailing silence burst. |
| WG-03 | The active subcarrier region SHALL be flanked by 8-bin lower and upper guard bands (DC and high-frequency protection). |
| WG-04 | Pilot subcarriers SHALL be inserted at every 8th active bin with the known value `1+1j`. |
| WG-05 | The number of active subcarriers (`n_tones`) SHALL be configurable at construction time (default: 100). |
| WG-06 | The modulated frame SHALL be amplitude-normalised to ±1 before transmission. |
| WG-07 | The demodulator SHALL correct carrier-frequency offset (CFO) using the Schmidl-Cox estimator: `φ = ∠Σ(r₂·r₁*)`, `f_cfo = φ/(2π·N)`, where `r₁`, `r₂` are the two received preamble windows and `N=32`. The estimator is unambiguous for \|f_cfo\| < f_s/(2N). |
| WG-08 | The demodulator SHALL perform frame timing recovery via cross-correlation with the known ZC preamble, using an adaptive threshold of `μ + 5σ`. When two peaks are detected, timing SHALL be anchored on the second peak (P2); when only one is detected it is treated as P1. |
| WG-09 | The demodulator SHALL estimate the per-subcarrier channel response using LS extraction at pilot positions and linear interpolation across all bins. |
| WG-10 | The demodulator SHALL apply zero-forcing equalization before returning data symbols. |
| WG-11 | The demodulator SHALL correct residual common-phase error after equalization by computing the mean phase deviation of equalized pilots from the expected `1+1j` and counter-rotating all subcarriers. |
| WG-12 | The modulator SHALL raise `ValueError` if the number of input symbols exceeds the available data subcarriers. |

### 2.2 PlutoSDR Transmitter

| ID | Requirement |
|---|---|
| TX-01 | The system SHALL connect to a PlutoSDR via a configurable URI (USB or Ethernet/IP). |
| TX-02 | The transmitter SHALL scale the complex baseband signal to 16-bit integer range (`2^14`) before passing it to the hardware. |
| TX-03 | The transmitter SHALL operate in cyclic buffer mode, repeating the loaded waveform continuously until explicitly stopped. |
| TX-04 | A `stop_transmit()` method SHALL destroy the TX buffer and halt continuous transmission. |
| TX-05 | The receiver SHALL flush a minimum of 5 stale hardware buffers before capturing a sample block, to avoid transient artefacts. |
| TX-06 | Received samples SHALL be normalised to ±1 before being returned to the caller. |
| TX-07 | All radio parameters (center frequency, sample rate, TX/RX gain, buffer size) SHALL be configurable at construction time. |

---

## 3. Parameters

### 3.1 OFDM Parameters

| Parameter | Symbol | Default | Notes |
|---|---|---|---|
| Number of active subcarriers | `n_tones` | 100 | Pilots + data bins, excluding guards |
| Guard band width (each side) | — | 8 bins | Lower (DC) and upper (alias) protection |
| Pilot spacing | — | Every 8th bin | Within the active region |
| Pilot value | — | `1+1j` | Known transmitted value for LS estimation |
| Preamble type | — | Zadoff-Chu | Root index `u=31`, length `n=32` |
| Silence padding | — | 32 samples | Pre- and post-frame |
| Frame length | — | `128 + n_tones` samples | `32 + 32 + 32 + (n_tones+16) + 32` |

### 3.2 OFDMModulator Parameters

| Parameter | Default | Notes |
|---|---|---|
| `n_tones` | (required) | Total FFT size |
| `cp_len` | 128 | Cyclic prefix length in samples |
| `pilot_bins` | `[50, 98, 111, 200, 350, 500, 650, 800, 950]` | Absolute bin indices |
| `pilot_val` | `1+0j` | Known pilot value |
| Data start bin | 100 | Data symbols placed from bin 100 onwards |
| Output scaling | `2^14` | Maps ±1 normalised signal to int16 range |

### 3.3 Radio Parameters

| Parameter | Default | Notes |
|---|---|---|
| Center frequency | 915 MHz | ISM band; must match TX and RX |
| Sample rate | 1 MSPS | Also sets RF bandwidth |
| TX hardware gain | −20 dB | Negative = attenuation |
| RX hardware gain | 30 dB | Manual gain control |
| Buffer size | 16 384 samples | ~16 ms at 1 MSPS |
| TX mode | Cyclic | Loops waveform until destroyed |

---

## 4. Frame Structure

```
Sample index →
┌────────────┬─────────────┬─────────────┬──────────────────────────┬────────────┐
│ silence    │ ZC preamble │ ZC preamble │     OFDM data symbol     │ silence    │
│  (32 samp) │  (32 samp)  │  (32 samp)  │   (n_tones + 16 samp)    │  (32 samp) │
└────────────┴─────────────┴─────────────┴──────────────────────────┴────────────┘
```

**OFDM symbol subcarrier layout:**

```
Bin index →
┌──────────┬────────────────────────────────────────────┬──────────┐
│  Guard   │         Active region (n_tones bins)        │  Guard   │
│  8 bins  │  [pilot] data data ... data [pilot] data …  │  8 bins  │
└──────────┴────────────────────────────────────────────┴──────────┘
              Pilots at every 8th bin (value = 1+1j)
```

---

## 5. Interfaces

### `OFDM`

```python
OFDM(n_tones: int = 100)

# Modulate complex symbols → time-domain frame
.modulate(symbols: np.ndarray) -> np.ndarray

# Demodulate received frame → recovered data symbols
.demodulate(y: np.ndarray) -> np.ndarray
```

### `OFDMModulator`

```python
OFDMModulator(n_tones, cp_len=128, pilot_bins=None, pilot_val=1+0j)

# Modulate amplitude array → time-domain symbol with CP, scaled to int16
.modulate(x_amps: np.ndarray) -> np.ndarray   # shape (-1, 1)

# Demodulate received buffer → equalized frequency-domain bins
.demod(x: np.ndarray) -> np.ndarray
```

### `PlutoSDR`

```python
PlutoSDR(uri, center_freq=915_000_000, sample_rate=1_000_000,
         tx_gain=-20, rx_gain=30, buffer_size=16384)

# Transmit IQ waveform (cyclic until stopped)
.transmit(iq: np.ndarray) -> None

# Stop cyclic transmission
.stop_transmit() -> None

# Capture one receive buffer, normalised to ±1
.receive() -> np.ndarray
```

---

## 6. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NF-01 | All waveform generation and demodulation SHALL operate without hardware present (pure NumPy). |
| NF-02 | The `OFDM` and `PlutoSDR` classes SHALL be independently unit-testable. |
| NF-03 | The system SHOULD support future extension to frequency-hopping by parameterising `center_freq` at transmit time. |
| NF-04 | TX/RX center frequencies MUST be identical for coherent demodulation. |

---

## 7. Out of Scope

- Forward error correction (FEC) / channel coding.
- Multi-antenna (MIMO) operation.
- Encryption or authentication of the transmitted data.
- Real-time scheduling or hard latency guarantees.
