# AGENTS.md

Guidance for AI coding agents working on this repository.

---

## Project Summary

This project generates OFDM baseband waveforms in software and transmits them over the air using an ADALM-PLUTO (PlutoSDR) software-defined radio.

- **Waveform generation** — `src/OFDM.py` (primary) and `src/OFDMModulator.py` (alternate)
- **Radio TX/RX** — `src/PlutoSDR.py` (thin wrapper over `pyadi-iio`)
- **Entry point** — `main.py` (loopback demo: generate → transmit → receive → demodulate)

See `docs/architecture.md` for a component breakdown and data-flow diagram.  
See `docs/spec.md` for functional requirements and parameter tables.

---

## Environment Setup

A virtual environment is expected at `venv/`. Activate it before running anything:

```bash
source venv/bin/activate
```

Install dependencies (there is no `requirements.txt` yet — install manually if needed):

```bash
pip install numpy matplotlib pyadi-iio pytest
```

> **Note:** `pyadi-iio` requires `libiio` to be installed on the host. Tests mock the hardware so the SDR driver does **not** need to be present to run the test suite.

---

## Running Tests

```bash
pytest
```

Tests live in `tests/`. Hardware is fully mocked — no PlutoSDR needs to be attached.

- `tests/test_ofdm.py` — unit tests for `OFDM` (preamble, subcarrier mapping, modulate/demodulate pipeline)
- `tests/test_plutosdr.py` — unit tests for `PlutoSDR` (init, transmit, receive) using `unittest.mock`

To run a single file:

```bash
pytest tests/test_ofdm.py -v
```

---

## Running the Demo

A PlutoSDR reachable at `ip:192.168.8.93` is required:

```bash
python3 main.py
```

The script transmits a 4-symbol OFDM frame and plots the received I/Q waveform.

---

## Code Conventions

- **Python 3.10+**; type hints used in `OFDM.py` and `PlutoSDR.py`.
- All array math uses `numpy`; no external DSP libraries.
- Private methods are prefixed with `_`. Do not call them from outside the class or tests that specifically target internals.
- `OFDM` is the canonical modem. Prefer it over `OFDMModulator` for new work unless you specifically need the alternate subcarrier layout or cyclic-prefix behaviour.
- Do not add hardware-dependent code to `OFDM.py` — it must remain importable without `pyadi-iio`.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Dual ZC preamble in every frame | Enables CFO estimation from the phase difference between two identical sequences. |
| 8-bin guard bands each side | Prevents spectral leakage into DC and aliases at the ADC/DAC boundary. |
| Pilots at every 8th active bin | Sparse enough to leave most subcarriers for data; dense enough for accurate linear interpolation of the channel. |
| Cyclic TX buffer on PlutoSDR | Waveform loops continuously without repeated host-to-device transfers, reducing jitter. |
| Hardware mocked in tests | Allows CI to run without SDR hardware; `unittest.mock.patch("src.PlutoSDR.adi")` replaces the `adi` module entirely. |

---

## Out of Scope

Do not add the following without explicit instruction:

- Forward error correction (FEC) or channel coding
- Multi-antenna (MIMO) support
- Encryption or authentication of transmitted data
- Real-time / hard-latency scheduling
