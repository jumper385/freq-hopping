import numpy as np

try:
    import adi
except Exception:  # libiio may be unavailable in non-hardware test environments
    adi = None

class PlutoSDR:
    """Minimal PlutoSDR wrapper for TX/RX over pyadi-iio."""

    def __init__(
        self,
        uri: str,
        center_freq: int = 915_000_000,
        sample_rate: int = 1_000_000,
        tx_gain: int = 0,
        rx_gain: int = 30,
        buffer_size: int = 1024 * 16,
    ):
        if adi is None:
            raise ImportError("pyadi-iio/libiio is not available; install libiio before using PlutoSDR hardware")
        self.sdr = adi.Pluto(uri=uri)
        self.sdr.sample_rate = sample_rate
        self.sdr.rx_rf_bandwidth = sample_rate
        self.sdr.tx_rf_bandwidth = sample_rate
        self.sdr.rx_lo = center_freq
        self.sdr.tx_lo = center_freq
        self.sdr.tx_hardwaregain_chan0 = tx_gain
        self.sdr.gain_control_mode_chan0 = "manual"
        self.sdr.rx_hardwaregain_chan0 = rx_gain
        self.sdr.rx_buffer_size = buffer_size
        self.sdr.tx_cyclic_buffer = True

    def transmit(self, iq: np.ndarray) -> None:
        """Send a complex baseband signal.  Scales to 16-bit integer range."""
        peak = np.max(np.abs(iq))
        if peak > 0:
            iq = iq / peak
        self.sdr.tx(iq * 2**14)

    def stop_transmit(self):
        self.sdr.tx_destroy_buffer()

    def tune(self, center_freq: int) -> None:
        """Retune both TX and RX local oscillators to the same frequency."""
        self.sdr.rx_lo = center_freq
        self.sdr.tx_lo = center_freq

    def receive(self, flush: int = 5) -> np.ndarray:
        """Capture one buffer of complex samples, normalised to ±1."""

        for _ in range(flush):
            self.sdr.rx()

        samples = self.sdr.rx()
        return samples / 2**14