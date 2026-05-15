"""
Modem contract benchmarks.

Every modem in MODEMS is automatically tested against this suite.
To add a new modem: import it and append an instance to MODEMS.
"""
import numpy as np
import pytest

from src.modem import Modem, SyncDebug
from src.OFDM import OFDM


def qpsk_payload(n_rows: int, n_cols: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    constellation = np.array([1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j], dtype=complex)
    return rng.choice(constellation, size=(n_rows, n_cols))


# ---------------------------------------------------------------------------
# Register modems under test here
# ---------------------------------------------------------------------------
MODEMS = [
    OFDM(n_tones=50, cp_len=16, roll_off=0),
    OFDM(n_tones=50, cp_len=16, roll_off=8),
    OFDM(n_tones=100, cp_len=32, roll_off=8),
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(params=MODEMS, ids=[repr(m) for m in MODEMS])
def modem(request) -> Modem:
    return request.param


# ---------------------------------------------------------------------------
# Contract tests — every Modem subclass must pass these
# ---------------------------------------------------------------------------

class TestModemContract:
    def test_is_modem_subclass(self, modem: Modem):
        assert isinstance(modem, Modem)

    def test_data_tone_count_positive(self, modem: Modem):
        assert modem.data_tone_count > 0

    def test_burst_output_is_1d_complex(self, modem: Modem):
        payload = qpsk_payload(1, modem.data_tone_count)
        burst = modem.modulate_burst(payload)
        assert burst.ndim == 1
        assert np.iscomplexobj(burst)

    def test_demodulate_burst_shape(self, modem: Modem):
        payload = qpsk_payload(4, modem.data_tone_count, seed=1)
        burst = modem.modulate_burst(payload)
        recovered = modem.demodulate_burst(burst, 4)
        assert recovered.shape == payload.shape

    def test_ser_noiseless_single_symbol(self, modem: Modem):
        payload = qpsk_payload(1, modem.data_tone_count, seed=2)
        burst = modem.modulate_burst(payload)
        recovered = modem.demodulate_burst(burst, 1)
        dec_rx = np.sign(recovered.real) + 1j * np.sign(recovered.imag)
        dec_tx = np.sign(payload.real) + 1j * np.sign(payload.imag)
        ser = float(np.mean(dec_rx != dec_tx))
        assert ser == 0.0, f"SER={ser:.1%} on noiseless single-symbol loopback"

    def test_ser_noiseless_burst(self, modem: Modem):
        payload = qpsk_payload(8, modem.data_tone_count, seed=3)
        burst = modem.modulate_burst(payload)
        recovered = modem.demodulate_burst(burst, 8)
        dec_rx = np.sign(recovered.real) + 1j * np.sign(recovered.imag)
        dec_tx = np.sign(payload.real) + 1j * np.sign(payload.imag)
        ser = float(np.mean(dec_rx != dec_tx))
        assert ser == 0.0, f"SER={ser:.1%} on noiseless 8-symbol burst loopback"

    def test_sync_debug_returns_sync_debug(self, modem: Modem):
        payload = qpsk_payload(1, modem.data_tone_count)
        burst = modem.modulate_burst(payload)
        dbg = modem.sync_debug(burst)
        assert isinstance(dbg, SyncDebug)

    def test_sync_debug_corr_mag_non_negative(self, modem: Modem):
        payload = qpsk_payload(1, modem.data_tone_count)
        burst = modem.modulate_burst(payload)
        dbg = modem.sync_debug(burst)
        if len(dbg.corr_mag):
            assert np.all(dbg.corr_mag >= 0)

    def test_sync_debug_threshold_non_negative(self, modem: Modem):
        payload = qpsk_payload(1, modem.data_tone_count)
        burst = modem.modulate_burst(payload)
        dbg = modem.sync_debug(burst)
        assert dbg.threshold >= 0
