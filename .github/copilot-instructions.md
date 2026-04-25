# Copilot Instructions

This repo generates OFDM baseband waveforms in software and transmits them over the air using an ADALM-PLUTO (PlutoSDR) software-defined radio.

Before doing any work, read:
- `AGENTS.md` — project summary, environment setup, code conventions, and out-of-scope items.
- `docs/architecture.md` — component breakdown, data-flow diagram, and dependency table.
- `docs/spec.md` — functional requirements and parameter tables.

## Hard Rules

- `src/OFDM.py` must **not** import `pyadi-iio` or any hardware-dependent library. It must be importable without SDR drivers present.
- Prefer `src/OFDM.py` over `src/OFDMModulator.py` for all new waveform work.
- All array math uses `numpy` only — no external DSP libraries.
- Private methods are prefixed with `_`. Do not call them from outside the class unless writing tests that specifically target internals.
- Do **not** add: FEC/channel coding, MIMO, encryption, real-time scheduling, or any other feature listed as out-of-scope in `AGENTS.md`.

## Testing

Hardware is fully mocked. Run the test suite with:

```bash
source venv/bin/activate
pytest
```

No PlutoSDR needs to be attached.
