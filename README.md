# freq-hopping

OFDM baseband waveform generation and over-the-air transmission with an ADALM-PLUTO (PlutoSDR) software-defined radio.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install numpy matplotlib pyadi-iio pytest
```

## Running tests

Hardware is fully mocked — no SDR needed.

```bash
pytest
```

## Project layout

```
src/
  modem.py        — Modem ABC (the contract every comms system must satisfy)
  OFDM.py         — Primary OFDM modem (implements Modem)
  PlutoSDR.py     — Thin pyadi-iio wrapper
main.py           — Loopback demo: generate → TX → RX → demodulate → plot
monitor.py        — Live 3-panel monitor: I/Q waveform · ZC correlation · constellation
tests/
  test_modem.py   — Modem contract benchmarks (run against every registered modem)
  test_ofdm.py    — OFDM-specific unit tests
  test_ofdm_throughput.py — Frame accounting and throughput benchmarks
```

---

## Writing a new baseband comms system

All modem implementations subclass `Modem` from `src/modem.py` and implement three members.  Once that's done the modem drops straight into the contract benchmarks and `monitor.py` with a one-line change.

### The contract

```python
# src/modem.py
class Modem(ABC):

    @property
    @abstractmethod
    def data_tone_count(self) -> int:
        """Number of payload-carrying subcarriers per symbol."""

    @abstractmethod
    def modulate_burst(self, symbols_matrix: np.ndarray) -> np.ndarray:
        """(n_symbols, data_tone_count) complex → 1-D time-domain burst."""

    @abstractmethod
    def demodulate_burst(self, y: np.ndarray, n_symbols: int) -> np.ndarray:
        """1-D received samples → (n_symbols, data_tone_count) complex."""

    # Optional — override to populate the monitor's correlation/timing overlay.
    def sync_debug(self, y: np.ndarray) -> SyncDebug:
        return SyncDebug()   # empty = overlay stays blank
```

`SyncDebug` carries four fields that `monitor.py` reads for its plots:

| Field | Type | Used for |
|---|---|---|
| `corr_mag` | `ndarray` | correlation plot |
| `threshold` | `float` | correlation threshold line |
| `peaks` | `ndarray[int]` | peak count in the status line |
| `pair` | `tuple[int,int] \| None` | P1/P2 marker positions on the I/Q waveform |

All fields default to empty/zero, so the monitor degrades gracefully if you don't override `sync_debug`.

---

### Toy example — single-carrier passthrough

This is the smallest possible modem that satisfies the contract.  It has no framing overhead, no channel equalisation, and no synchronisation — it works perfectly in a noiseless software loopback but will be terrible over the air.  It exists purely to show the interface.

```python
# src/sc_passthrough.py
import numpy as np
from src.modem import Modem


class SCPassthrough(Modem):
    """
    Minimal single-carrier passthrough modem.

    modulate_burst  : flatten → normalise → return
    demodulate_burst: slice the first n_symbols * data_tone_count samples and reshape
    """

    def __init__(self, n_tones: int = 43):
        self._n_tones = n_tones

    def __repr__(self) -> str:
        return f"SCPassthrough(n_tones={self._n_tones})"

    @property
    def data_tone_count(self) -> int:
        return self._n_tones

    def modulate_burst(self, symbols_matrix: np.ndarray) -> np.ndarray:
        flat = symbols_matrix.flatten().astype(complex)
        peak = float(np.max(np.abs(flat))) or 1.0
        return flat / peak

    def demodulate_burst(self, y: np.ndarray, n_symbols: int) -> np.ndarray:
        n = n_symbols * self._n_tones
        return y[:n].reshape(n_symbols, self._n_tones)
```

#### Register in the contract benchmarks

Open `tests/test_modem.py` and add the new modem to `MODEMS`:

```python
from src.sc_passthrough import SCPassthrough

MODEMS = [
    OFDM(n_tones=50, cp_len=16, roll_off=0),
    OFDM(n_tones=50, cp_len=16, roll_off=8),
    OFDM(n_tones=100, cp_len=32, roll_off=8),
    SCPassthrough(),           # ← new
]
```

Run `pytest tests/test_modem.py` — all contract tests run against every modem in the list automatically.

#### Swap into monitor.py

Two lines at the top of `monitor.py`:

```python
from src.sc_passthrough import SCPassthrough   # ← change import
...
modem: Modem = SCPassthrough()                 # ← change instance
```

Everything else — SDR setup, SER calculation, all three plot panels — works unchanged.

---

### What to build next

Once the passthrough works in loopback, typical next steps are:

1. **Framing** — prepend a sync word or ZC preamble so `demodulate_burst` can find the payload boundary in a real received buffer.
2. **Channel estimation** — insert known pilots; interpolate to equalise the received subcarriers.
3. **CFO correction** — use a dual-preamble Schmidl-Cox estimator; return `corr_mag`/`threshold`/`pair` from `sync_debug` to get the monitor overlay for free.
4. **Override `sync_debug`** — once you have sync internals, populate `SyncDebug` so the live monitor shows your modem's correlation peak and frame markers.

See `src/OFDM.py` for a complete reference implementation of all four steps.
