# Project Specification

## 1. Purpose

Generate OFDM baseband waveforms in software and transmit them over the air using an ADALM-PLUTO (PlutoSDR) software-defined radio. The system must support both standalone waveform generation (no hardware required) and live over-the-air TX/RX loopback testing.

---

## 2. Functional Requirements

### 2.1 OFDM Waveform Generator

| ID | Requirement |
|---|---|
| WG-01 | The system SHALL generate a baseband OFDM frame from an arbitrary array of complex input symbols. |
| WG-02 | The frame SHALL consist of a leading silence burst, two back-to-back Zadoff-Chu preambles, a cyclic-prefix-prefixed OFDM data symbol (with optional cyclic suffix when windowing is enabled), and a trailing silence burst. |
| WG-03 | The active subcarrier region SHALL be flanked by 8-bin lower and upper guard bands (DC and high-frequency protection). |
| WG-04 | Pilot subcarriers SHALL be inserted at every 8th active bin with the known value `1+1j`. |
| WG-05 | The number of active subcarriers (`n_tones`), cyclic prefix length (`cp_len`), and window roll-off length (`roll_off`) SHALL be configurable at construction time. |
| WG-06 | The modulated frame SHALL be amplitude-normalised to ±1 before transmission. |
| WG-07 | The demodulator SHALL correct carrier-frequency offset (CFO) using the Schmidl-Cox estimator: `φ = ∠Σ(r₂·r₁*)`, `f_cfo = φ/(2π·N)`, where `r₁`, `r₂` are the two received preamble windows and `N=32`. The estimator is unambiguous for \|f_cfo\| < f_s/(2N). |
| WG-08 | The demodulator SHALL perform frame timing recovery via ZC cross-correlation with an adaptive threshold of `μ + 5σ`. Peak detection SHALL use rising-edge detection — only the first sample where the correlation magnitude crosses the threshold upward is recorded per physical peak, giving one index per preamble occurrence. `_find_preamble_pair` SHALL then scan the resulting indices for the first consecutive pair with spacing in the range `[30, 34]` samples (nominal 32 ±2 tolerance) to identify P1 and P2. The ±2 tolerance absorbs the single-sample jitter caused by the Pluto cyclic-DMA loop-boundary transient. Timing SHALL be anchored on P2 (`data_start = P2 + 32`). If no valid pair is found and only one peak is present it is treated as P1. |
| WG-09 | The demodulator SHALL remove the cyclic prefix (and cyclic suffix if `roll_off > 0`) before applying the FFT. |
| WG-10 | The demodulator SHALL estimate per-subcarrier noise variance from the received power in the zero-transmitted guard-band bins (`σ² = mean(|Y[k]|²)` for guard bins). |
| WG-11 | The demodulator SHALL estimate the per-subcarrier channel response using LS extraction at pilot positions and linear interpolation across all bins. |
| WG-12 | The demodulator SHALL apply LMMSE equalization: `X̂[k] = H*[k]·Y[k] / (|H[k]|² + σ²)`. When `σ² = 0` this reduces to zero-forcing. |
| WG-13 | The demodulator SHALL correct residual common-phase error after equalization by computing the mean phase deviation of equalized pilots from the expected `1+1j` and counter-rotating all subcarriers. |
| WG-14 | The modulator SHALL raise `ValueError` if the number of input symbols exceeds the available data subcarriers. |
| WG-15 | The modem SHALL provide `modulate_burst(symbols_matrix)` and `demodulate_burst(y, n_symbols)` methods that pack/unpack N OFDM symbols under a single preamble pair. Each symbol in a burst SHALL have its own CP and independent equalization pass on receive. |

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
| Number of active subcarriers | `n_tones` | 50 | Pilots + data bins, excluding guards |
| Cyclic prefix length | `cp_len` | 16 samples | Protects against multipath delay spreads up to `cp_len` samples (~16 µs at 1 MSPS) |
| Window roll-off length | `roll_off` | 0 (disabled) | Raised-cosine CS taper; set to e.g. 8 to reduce OOB leakage |
| Guard band width (each side) | — | 8 bins | Lower (DC) and upper (alias) protection; also used for noise variance estimation |
| Pilot spacing | — | Every 8th bin | Within the active region |
| Pilot value | — | `1+1j` | Known transmitted value for LS estimation |
| Preamble type | — | Zadoff-Chu | Root index `u=31`, length `n=32` |
| Silence padding | — | 32 samples | Pre- and post-frame |
| Single-symbol frame length | — | `128 + n_tones + cp_len + roll_off` samples | `32 + 32 + 32 + (n_tones+16+cp_len+roll_off) + 32` |

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

**Single-symbol frame:**

```
Sample index →
┌────────────┬─────────────┬─────────────┬──────────┬──────────────────────┬───────────┬────────────┐
│ silence    │ ZC preamble │ ZC preamble │ CP       │ OFDM data symbol     │ CS        │ silence    │
│ (32 samp)  │  (32 samp)  │  (32 samp)  │(cp_len)  │  (n_tones + 16 samp) │(roll_off) │ (32 samp)  │
└────────────┴─────────────┴─────────────┴──────────┴──────────────────────┴───────────┴────────────┘
```

CS (cyclic suffix) is only present when `roll_off > 0`.

**Multi-symbol burst frame** (N symbols, single preamble pair):

```
Sample index →
┌──────────┬───────────┬───────────┬───────────────────┬───────────┬──────────┐
│ silence  │ ZC preamble │ ZC preamble │ [CP|sym_0|CS] [CP|sym_1|CS] … │ [CP|sym_N|CS] │ silence  │
└──────────┴───────────┴───────────┴───────────────────┴───────────┴──────────┘
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
OFDM(n_tones: int = 50, cp_len: int = 16, roll_off: int = 0)

# Modulate complex symbols → single-symbol time-domain frame
.modulate(symbols: np.ndarray) -> np.ndarray

# Demodulate received single-symbol frame → recovered data symbols
.demodulate(y: np.ndarray) -> np.ndarray

# Modulate N rows of symbols → burst frame (one preamble pair, N CP-prefixed symbols)
.modulate_burst(symbols_matrix: np.ndarray) -> np.ndarray   # shape (n_syms, data_tones)

# Demodulate burst frame → recovered symbols per row
.demodulate_burst(y: np.ndarray, n_symbols: int) -> np.ndarray   # shape (n_symbols, data_tones)
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
