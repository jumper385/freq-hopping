import numpy as np
from src.modem import Modem, SyncDebug
from src.utils.preambles import zc, zc_correlation, AdaptiveThreshold

class PreambleModem(Modem):
    """
    modem used to characterize preamble performance in isolation from data symbol processing. It simply
    generates and correlates preambles without handling actual data symbols.
    """

    def __init__(self, preamble_len: int = 32, silence_len: int = 32, pair_tolerance: int = 0, adaptive_threshold_multiplier: float = 4.0):
        self._preamble_len = preamble_len
        self._pair_tolerance = pair_tolerance
        self._preamble = zc(preamble_len)
        self._silence = np.zeros(silence_len, dtype=complex)
        self._adaptive_threshold_multiplier = adaptive_threshold_multiplier
        self.dbg_instrument : dict | None = None # dict

    def __repr__(self) -> str:
        return f"PreambleModem(preamble_len={self._preamble_len}, silence_len={len(self._silence)})"

    @property
    def data_tone_count(self) -> int:
        return 0

    def modulate_burst(self, symbols_matrix: np.ndarray) -> np.ndarray:
        sig = np.concatenate([self._preamble, self._preamble, self._silence])
        sig_max = np.max(np.abs(sig))
        return sig / sig_max if sig_max > 0 else sig

    def demodulate_burst(self, y: np.ndarray, n_symbols: int) -> np.ndarray:
        # This modem carries no data symbols, so there is nothing to recover.
        # Returns an empty array of shape (n_symbols, 0) to satisfy the Modem
        # contract. All useful output — correlation magnitude, threshold, and
        # the detected P1/P2 pair — comes from sync_debug(), not here.
        return np.empty((n_symbols, 0), dtype=complex)

    def sync_debug(self, y: np.ndarray) -> SyncDebug:
        corr_mag = np.abs(zc_correlation(y, self._preamble))
        adaptive_threshold = AdaptiveThreshold(std_multiplier=self._adaptive_threshold_multiplier)
        adaptive_threshold.update(corr_mag)
        threshold = adaptive_threshold.compute_threshold()

        # Find the first sample of each contiguous run above threshold.
        # np.diff on a boolean mask is +1 at a rising edge and -1 at a falling edge.
        mask = corr_mag > threshold
        rising_edges = np.where(np.diff(mask.astype(int)) > 0)[0] + 1
        if len(mask) > 0 and mask[0]:
            rising_edges = np.concatenate([[0], rising_edges])

        # Collect all pairs of rising edges whose spacing is within ±pair_tolerance of preamble_len.
        pair_list = []
        ave_delta = 0;
        for i in range(len(rising_edges) - 1):
            delta = rising_edges[i+1] - rising_edges[i]
            min_delta = self._preamble_len - self._pair_tolerance
            max_delta = self._preamble_len + self._pair_tolerance
            if min_delta <= delta <= max_delta:
                ave_delta += delta
                pair_list.append((rising_edges[i], rising_edges[i+1]))

        if pair_list:
            ave_delta /= len(pair_list)

        # average calculate amrgin  = (peak - threshold)/threshold
        peak_mag = np.max(corr_mag)
        mean_margin = (peak_mag - threshold) / threshold

        self.dbg_instrument = {
            "pair_detection_count": len(pair_list),
            "has_detections": bool(pair_list),
            "ave_pair_spacing": ave_delta,
            "mean_margin": mean_margin,
        }

        return SyncDebug(corr_mag=corr_mag, threshold=threshold, peaks=rising_edges, pair=pair_list if pair_list else None)