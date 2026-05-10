import numpy as np
import pytest

from src.OFDM import OFDM


SAMPLE_RATE = 1_000_000
QPSK_BITS_PER_SYMBOL = 2


def qpsk_payload(n_rows: int, n_cols: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    constellation = np.array([1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j], dtype=complex)
    return rng.choice(constellation, size=(n_rows, n_cols))


class TestBasebandThroughputAccounting:
    def test_default_payload_and_frame_accounting(self):
        ofdm = OFDM(n_tones=50, cp_len=16, roll_off=0)

        assert ofdm.fft_len == 66
        assert ofdm.data_tone_count == 43  # 50 active tones minus pilots at 0,8,...,48
        assert ofdm.symbol_block_len == 82
        assert ofdm.sync_overhead_len == 128
        assert ofdm.frame_len(n_symbols=1) == len(ofdm.modulate(np.ones(ofdm.data_tone_count)))

    def test_single_symbol_qpsk_throughput_matches_frame_length(self):
        ofdm = OFDM(n_tones=50, cp_len=16, roll_off=0)

        expected_payload_bits = 43 * QPSK_BITS_PER_SYMBOL
        expected_frame_samples = 210
        expected_bps = expected_payload_bits * SAMPLE_RATE / expected_frame_samples

        assert ofdm.payload_bits_per_frame(QPSK_BITS_PER_SYMBOL) == expected_payload_bits
        assert ofdm.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL) == pytest.approx(expected_bps)
        assert expected_bps == pytest.approx(409_523.8095)

    def test_burst_framing_amortises_preamble_overhead(self):
        ofdm = OFDM(n_tones=50, cp_len=16, roll_off=0)

        single_bps = ofdm.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL, n_symbols=1)
        burst_bps = ofdm.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL, n_symbols=10)
        asymptotic_bps = ofdm.data_tone_count * QPSK_BITS_PER_SYMBOL * SAMPLE_RATE / ofdm.symbol_block_len

        assert ofdm.frame_len(n_symbols=10) == 948
        assert burst_bps == pytest.approx(907_172.9958)
        assert burst_bps > 2.0 * single_bps
        assert burst_bps < asymptotic_bps
        assert burst_bps / asymptotic_bps > 0.86

    def test_rolloff_windowing_has_explicit_throughput_cost(self):
        rectangular = OFDM(n_tones=50, cp_len=16, roll_off=0)
        windowed = OFDM(n_tones=50, cp_len=16, roll_off=8)

        assert windowed.symbol_block_len == rectangular.symbol_block_len + 8
        assert windowed.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL, n_symbols=10) < rectangular.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL, n_symbols=10)

    def test_invalid_throughput_parameters_raise(self):
        ofdm = OFDM()

        with pytest.raises(ValueError):
            ofdm.frame_len(n_symbols=0)
        with pytest.raises(ValueError):
            ofdm.payload_bits_per_frame(bits_per_symbol=0)
        with pytest.raises(ValueError):
            ofdm.theoretical_throughput_bps(sample_rate=0)


class TestBasebandBurstRoundtrip:
    def test_clean_burst_roundtrip_at_full_payload(self):
        ofdm = OFDM(n_tones=50, cp_len=16, roll_off=0)
        payload = qpsk_payload(n_rows=8, n_cols=ofdm.data_tone_count, seed=1)

        frame = ofdm.modulate_burst(payload)
        recovered = ofdm.demodulate_burst(frame, n_symbols=payload.shape[0])

        assert len(frame) == ofdm.frame_len(n_symbols=payload.shape[0])
        assert recovered.shape == payload.shape
        np.testing.assert_allclose(recovered, payload, atol=1e-10)

    def test_burst_roundtrip_with_cfo_and_awgn(self):
        ofdm = OFDM(n_tones=50, cp_len=16, roll_off=0)
        payload = qpsk_payload(n_rows=6, n_cols=ofdm.data_tone_count, seed=2)
        frame = ofdm.modulate_burst(payload)

        n = np.arange(len(frame))
        cfo = 0.0035
        impaired = frame * np.exp(1j * 2 * np.pi * cfo * n)

        rng = np.random.default_rng(3)
        noise = 0.015 * (rng.normal(size=len(frame)) + 1j * rng.normal(size=len(frame)))
        recovered = ofdm.demodulate_burst(impaired + noise, n_symbols=payload.shape[0])

        decisions = np.sign(recovered.real) + 1j * np.sign(recovered.imag)
        symbol_error_rate = np.mean(decisions != payload)
        assert symbol_error_rate < 0.02


class TestThroughputOptimisationScenarios:
    def test_larger_fft_with_same_cp_improves_payload_efficiency(self):
        baseline = OFDM(n_tones=50, cp_len=16, roll_off=0)
        wider = OFDM(n_tones=100, cp_len=16, roll_off=0)

        assert wider.data_tone_count == 87
        assert wider.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL, n_symbols=10) > baseline.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL, n_symbols=10)

    def test_bursting_is_a_bigger_win_than_small_cp_tuning_for_current_defaults(self):
        baseline = OFDM(n_tones=50, cp_len=16, roll_off=0)
        shorter_cp = OFDM(n_tones=50, cp_len=8, roll_off=0)

        cp_gain = shorter_cp.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL, n_symbols=1) / baseline.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL, n_symbols=1)
        burst_gain = baseline.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL, n_symbols=10) / baseline.theoretical_throughput_bps(SAMPLE_RATE, QPSK_BITS_PER_SYMBOL, n_symbols=1)

        assert cp_gain == pytest.approx(210 / 202)
        assert burst_gain > 2.0
        assert burst_gain > cp_gain
