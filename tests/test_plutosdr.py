import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from src.PlutoSDR import PlutoSDR


@pytest.fixture
def mock_pluto():
    """Bare MagicMock standing in for an adi.Pluto instance."""
    return MagicMock()


@pytest.fixture
def sdr(mock_pluto):
    """PlutoSDR constructed against the mock hardware."""
    with patch("src.PlutoSDR.adi") as mock_adi:
        mock_adi.Pluto.return_value = mock_pluto
        yield PlutoSDR(uri="usb:")


# ------------------------------------------------------------------
# __init__ / configuration
# ------------------------------------------------------------------

class TestInit:
    def test_pluto_constructed_with_uri(self, mock_pluto):
        with patch("src.PlutoSDR.adi") as mock_adi:
            mock_adi.Pluto.return_value = mock_pluto
            PlutoSDR(uri="ip:192.168.1.1")
        mock_adi.Pluto.assert_called_once_with(uri="ip:192.168.1.1")

    def test_sample_rate_applied(self, mock_pluto, sdr):
        assert mock_pluto.sample_rate == 1_000_000

    def test_rx_lo_applied(self, mock_pluto, sdr):
        assert mock_pluto.rx_lo == 915_000_000

    def test_tx_lo_applied(self, mock_pluto, sdr):
        assert mock_pluto.tx_lo == 915_000_000

    def test_rx_rf_bandwidth_equals_sample_rate(self, mock_pluto, sdr):
        assert mock_pluto.rx_rf_bandwidth == 1_000_000

    def test_tx_rf_bandwidth_equals_sample_rate(self, mock_pluto, sdr):
        assert mock_pluto.tx_rf_bandwidth == 1_000_000

    def test_tx_gain_applied(self, mock_pluto, sdr):
        assert mock_pluto.tx_hardwaregain_chan0 == -20

    def test_rx_gain_applied(self, mock_pluto, sdr):
        assert mock_pluto.rx_hardwaregain_chan0 == 30

    def test_gain_control_mode_is_manual(self, mock_pluto, sdr):
        assert mock_pluto.gain_control_mode_chan0 == "manual"

    def test_rx_buffer_size_applied(self, mock_pluto, sdr):
        assert mock_pluto.rx_buffer_size == 1024 * 16

    def test_custom_params_forwarded(self, mock_pluto):
        with patch("src.PlutoSDR.adi") as mock_adi:
            mock_adi.Pluto.return_value = mock_pluto
            PlutoSDR(
                uri="usb:",
                center_freq=2_400_000_000,
                sample_rate=2_000_000,
                tx_gain=-10,
                rx_gain=50,
                buffer_size=4096,
            )
        assert mock_pluto.rx_lo == 2_400_000_000
        assert mock_pluto.sample_rate == 2_000_000
        assert mock_pluto.tx_hardwaregain_chan0 == -10
        assert mock_pluto.rx_hardwaregain_chan0 == 50
        assert mock_pluto.rx_buffer_size == 4096

    def test_tune_updates_rx_and_tx_lo(self, mock_pluto, sdr):
        sdr.tune(916_000_000)
        assert mock_pluto.rx_lo == 916_000_000
        assert mock_pluto.tx_lo == 916_000_000


# ------------------------------------------------------------------
# transmit
# ------------------------------------------------------------------

class TestTransmit:
    def test_calls_sdr_tx(self, mock_pluto, sdr):
        sdr.transmit(np.array([0.5 + 0.5j, -0.5 + 0j]))
        mock_pluto.tx.assert_called_once()

    def test_scales_peak_to_2_14(self, mock_pluto, sdr):
        sdr.transmit(np.array([2.0 + 0j, 1.0 + 0j]))
        sent = mock_pluto.tx.call_args[0][0]
        assert np.max(np.abs(sent)) == pytest.approx(2**14)

    def test_unit_input_scales_to_2_14(self, mock_pluto, sdr):
        sdr.transmit(np.array([1.0 + 0j]))
        sent = mock_pluto.tx.call_args[0][0]
        assert np.max(np.abs(sent)) == pytest.approx(2**14)

    def test_zero_signal_does_not_raise(self, mock_pluto, sdr):
        sdr.transmit(np.zeros(8, dtype=complex))
        mock_pluto.tx.assert_called_once()

    def test_zero_signal_sent_as_zeros(self, mock_pluto, sdr):
        sdr.transmit(np.zeros(8, dtype=complex))
        sent = mock_pluto.tx.call_args[0][0]
        np.testing.assert_array_equal(sent, 0)

    def test_phase_preserved_after_normalisation(self, mock_pluto, sdr):
        sdr.transmit(np.array([0 + 3j, -3 + 0j]))
        sent = mock_pluto.tx.call_args[0][0]
        np.testing.assert_allclose(sent, [0 + 2**14 * 1j, -2**14 + 0j], atol=1e-9)


# ------------------------------------------------------------------
# receive
# ------------------------------------------------------------------

class TestReceive:
    def test_calls_sdr_rx_after_default_flushes(self, mock_pluto, sdr):
        mock_pluto.rx.return_value = np.zeros(16, dtype=complex)
        sdr.receive()
        assert mock_pluto.rx.call_count == 6

    def test_flush_can_be_disabled(self, mock_pluto, sdr):
        mock_pluto.rx.return_value = np.zeros(16, dtype=complex)
        sdr.receive(flush=0)
        mock_pluto.rx.assert_called_once()

    def test_normalises_by_2_14(self, mock_pluto, sdr):
        raw = np.array([float(2**14) + 0j, 0 - float(2**13) * 1j])
        mock_pluto.rx.return_value = raw
        result = sdr.receive()
        np.testing.assert_allclose(result, raw / 2**14)

    def test_output_is_complex(self, mock_pluto, sdr):
        mock_pluto.rx.return_value = np.ones(8, dtype=complex) * 2**14
        assert np.iscomplexobj(sdr.receive())

    def test_output_length_matches_input(self, mock_pluto, sdr):
        mock_pluto.rx.return_value = np.zeros(512, dtype=complex)
        assert len(sdr.receive()) == 512

