import pytest
import numpy as np
from src.OFDM import OFDM


@pytest.fixture
def ofdm():
    return OFDM()


@pytest.fixture
def symbols():
    return np.array([1 + 1j, 0 - 1j, 1.0 + 0j, 0 + 0.5j])


# ------------------------------------------------------------------
# _generate_preamble
# ------------------------------------------------------------------

class TestGeneratePreamble:
    def test_default_length(self, ofdm):
        assert len(ofdm._generate_preamble()) == 32

    def test_custom_length(self, ofdm):
        assert len(ofdm._generate_preamble(n=64)) == 64

    def test_unit_magnitude(self, ofdm):
        zc = ofdm._generate_preamble()
        np.testing.assert_allclose(np.abs(zc), 1.0)


# ------------------------------------------------------------------
# _construct_iframe
# ------------------------------------------------------------------

class TestConstructIframe:
    def test_output_length(self, ofdm, symbols):
        iframe = ofdm._construct_iframe(symbols)
        assert len(iframe) == ofdm.n_tones + 16

    def test_lower_guard_band_is_zero(self, ofdm, symbols):
        iframe = ofdm._construct_iframe(symbols)
        np.testing.assert_array_equal(iframe[:8], 0)

    def test_upper_guard_band_is_zero(self, ofdm, symbols):
        iframe = ofdm._construct_iframe(symbols)
        np.testing.assert_array_equal(iframe[-8:], 0)

    def test_pilot_values_correct(self, ofdm, symbols):
        iframe = ofdm._construct_iframe(symbols)
        active = iframe[8:-8]
        pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
        pilot_mask[::8] = True
        np.testing.assert_array_equal(active[pilot_mask], 1 + 1j)

    def test_data_symbols_placed(self, ofdm, symbols):
        iframe = ofdm._construct_iframe(symbols)
        active = iframe[8:-8]
        pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
        pilot_mask[::8] = True
        data_tones = active[~pilot_mask]
        np.testing.assert_array_equal(data_tones[:len(symbols)], symbols)

    def test_too_many_symbols_raises(self, ofdm):
        pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
        pilot_mask[::8] = True
        data_len = np.count_nonzero(~pilot_mask)
        with pytest.raises(ValueError):
            ofdm._construct_iframe(np.ones(data_len + 1, dtype=complex))


# ------------------------------------------------------------------
# modulate
# ------------------------------------------------------------------

class TestModulate:
    def test_frame_length(self, ofdm, symbols):
        frame = ofdm.modulate(symbols)
        symbol_len = ofdm.n_tones + 16 + ofdm.cp_len + ofdm.roll_off
        assert len(frame) == 32 + 32 + 32 + symbol_len + 32

    def test_leading_silence(self, ofdm, symbols):
        frame = ofdm.modulate(symbols)
        np.testing.assert_array_equal(frame[:32], 0)

    def test_trailing_silence(self, ofdm, symbols):
        frame = ofdm.modulate(symbols)
        np.testing.assert_array_equal(frame[-32:], 0)

    def test_preamble_repeated(self, ofdm, symbols):
        frame = ofdm.modulate(symbols)
        preamble = ofdm._generate_preamble()
        np.testing.assert_allclose(frame[32:64], preamble)
        np.testing.assert_allclose(frame[64:96], preamble)


# ------------------------------------------------------------------
# _preamble_detect
# ------------------------------------------------------------------

class TestPreambleDetect:
    def test_detects_at_least_two_peaks(self, ofdm, symbols):
        frame = ofdm.modulate(symbols)
        peaks = ofdm._preamble_detect(frame)
        assert len(peaks) >= 2

    def test_peak_separation_is_preamble_length(self, ofdm, symbols):
        frame = ofdm.modulate(symbols)
        peaks = ofdm._preamble_detect(frame)
        # the two back-to-back preambles should give a gap of exactly 32
        assert any(np.diff(peaks) == 32)

    def test_no_false_positives_in_noise_floor(self, ofdm):
        rng = np.random.default_rng(0)
        noise = rng.normal(scale=1e-6, size=200) + 1j * rng.normal(scale=1e-6, size=200)
        peaks = ofdm._preamble_detect(noise)
        assert len(peaks) == 0


# ------------------------------------------------------------------
# _find_all_preamble_pairs
# ------------------------------------------------------------------

class TestFindAllPreamblePairs:
    def test_returns_all_consecutive_pairs_within_tolerance(self, ofdm):
        peaks = np.array([10, 42, 74, 120, 151])
        assert ofdm._find_all_preamble_pairs(peaks) == [(10, 42), (42, 74), (120, 151)]

    def test_rejects_nonconsecutive_or_out_of_tolerance_pairs(self, ofdm):
        peaks = np.array([10, 41, 80, 112])
        assert ofdm._find_all_preamble_pairs(peaks) == [(10, 41), (80, 112)]

    def test_single_candidate_api_still_returns_first_pair(self, ofdm):
        peaks = np.array([10, 42, 74])
        assert ofdm._find_preamble_pair(peaks) == (10, 42)


# ------------------------------------------------------------------
# _cancel_cfo
# ------------------------------------------------------------------

class TestCancelCfo:
    def test_no_preamble_returns_unchanged(self, ofdm):
        # pure low-amplitude noise — no valid preamble
        rng = np.random.default_rng(1)
        noise = rng.normal(scale=1e-9, size=300) + 1j * rng.normal(scale=1e-9, size=300)
        result = ofdm._cancel_cfo(noise)
        np.testing.assert_array_equal(result, noise)

    def test_clean_frame_unchanged(self, ofdm, symbols):
        # preamble separation is exactly 32 → estimated_cfo = 0 → identity correction
        frame = ofdm.modulate(symbols)
        corrected = ofdm._cancel_cfo(frame)
        np.testing.assert_allclose(corrected, frame, atol=1e-10)

    def test_output_length_preserved(self, ofdm, symbols):
        frame = ofdm.modulate(symbols)
        assert len(ofdm._cancel_cfo(frame)) == len(frame)


# ------------------------------------------------------------------
# _estimate_channel
# ------------------------------------------------------------------

class TestEstimateChannel:
    @pytest.fixture
    def freq_vector(self, ofdm, symbols):
        """Perfect freq-domain vector (no channel, no noise)."""
        iframe = ofdm._construct_iframe(symbols)
        return np.fft.fft(np.fft.ifft(iframe))

    def test_output_length(self, ofdm, freq_vector):
        h = ofdm._estimate_channel(freq_vector)
        assert len(h) == len(freq_vector)

    def test_unity_channel_at_pilot_bins(self, ofdm, freq_vector):
        # With H=1 throughout, the estimate at every pilot should equal 1
        h = ofdm._estimate_channel(freq_vector)
        pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
        pilot_mask[::8] = True
        pilot_bins = np.where(pilot_mask)[0] + 8
        np.testing.assert_allclose(h[pilot_bins], 1.0 + 0j, atol=1e-10)

    def test_known_flat_channel_recovered_at_pilots(self, ofdm, symbols):
        # Apply a known flat channel H_true = 2 - 0.5j, then estimate it
        h_true = 2.0 - 0.5j
        iframe = ofdm._construct_iframe(symbols)
        y_freq = np.fft.fft(np.fft.ifft(iframe)) * h_true
        h = ofdm._estimate_channel(y_freq)
        pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
        pilot_mask[::8] = True
        pilot_bins = np.where(pilot_mask)[0] + 8
        np.testing.assert_allclose(h[pilot_bins], h_true, atol=1e-10)

    def test_flat_channel_interpolates_uniformly(self, ofdm, symbols):
        # With a flat channel, all interpolated bins should equal H_true
        h_true = 1.5 + 0.3j
        iframe = ofdm._construct_iframe(symbols)
        y_freq = np.fft.fft(np.fft.ifft(iframe)) * h_true
        h = ofdm._estimate_channel(y_freq)
        # active subcarriers (between guard bands) should all be close to h_true
        np.testing.assert_allclose(h[8:-8], h_true, atol=1e-10)

    def test_frequency_selective_channel_recovered_at_pilots(self, ofdm, symbols):
        # Each pilot sees a different H; estimate should match at those positions
        iframe = ofdm._construct_iframe(symbols)
        freqs_tx = np.fft.fft(np.fft.ifft(iframe))
        rng = np.random.default_rng(42)
        h_true = rng.normal(size=len(freqs_tx)) + 1j * rng.normal(size=len(freqs_tx))
        y_freq = freqs_tx * h_true
        h_est = ofdm._estimate_channel(y_freq)
        pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
        pilot_mask[::8] = True
        pilot_bins = np.where(pilot_mask)[0] + 8
        np.testing.assert_allclose(h_est[pilot_bins], h_true[pilot_bins], atol=1e-10)


# ------------------------------------------------------------------
# _equalize
# ------------------------------------------------------------------

class TestEqualize:
    def test_output_length(self, ofdm, symbols):
        iframe = ofdm._construct_iframe(symbols)
        y = np.fft.fft(np.fft.ifft(iframe))
        h = np.ones(len(y), dtype=complex)
        assert len(ofdm._equalize(y, h)) == len(y)

    def test_unity_h_returns_input_unchanged(self, ofdm, symbols):
        iframe = ofdm._construct_iframe(symbols)
        y = np.fft.fft(np.fft.ifft(iframe))
        h = np.ones(len(y), dtype=complex)
        np.testing.assert_allclose(ofdm._equalize(y, h), y, atol=1e-15)

    def test_flat_channel_inversion(self, ofdm, symbols):
        # apply H everywhere then equalize → should recover the original
        iframe = ofdm._construct_iframe(symbols)
        y = np.fft.fft(np.fft.ifft(iframe))
        h_true = (1.5 + 0.3j) * np.ones(len(y), dtype=complex)
        np.testing.assert_allclose(ofdm._equalize(y * h_true, h_true), y, atol=1e-10)

    def test_estimate_then_equalize_roundtrip(self, ofdm, symbols):
        # estimate H from a flat-channel signal, then equalize → recover original
        h_true = 2.0 - 0.5j
        iframe = ofdm._construct_iframe(symbols)
        y = np.fft.fft(np.fft.ifft(iframe)) * h_true
        h_est = ofdm._estimate_channel(y)
        equalized = ofdm._equalize(y, h_est)
        # active pilots should recover to 1+1j after equalization
        pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
        pilot_mask[::8] = True
        active = equalized[8:-8]
        np.testing.assert_allclose(active[pilot_mask], 1 + 1j, atol=1e-10)


# ------------------------------------------------------------------
# demodulate (integration)
# ------------------------------------------------------------------

class TestDemodulate:
    def test_output_length(self, ofdm, symbols):
        frame = ofdm.modulate(symbols)
        recovered = ofdm.demodulate(frame)
        pilot_mask = np.zeros(ofdm.n_tones, dtype=bool)
        pilot_mask[::8] = True
        assert len(recovered) == np.count_nonzero(~pilot_mask)

    def test_roundtrip_clean(self, ofdm, symbols):
        frame = ofdm.modulate(symbols)
        recovered = ofdm.demodulate(frame)
        np.testing.assert_allclose(recovered[:len(symbols)], symbols, atol=1e-10)

    def test_cfo_estimate_zero_for_clean_frame(self, ofdm, symbols):
        # Schmidl-Cox: for a clean frame the two preambles are identical so
        # sum(r2 * conj(r1)) is real and positive → phi = 0 → cfo = 0.
        frame = ofdm.modulate(symbols)
        peaks = ofdm._preamble_detect(frame)
        assert len(peaks) >= 2
        r1 = frame[int(peaks[0]) : int(peaks[0]) + 32]
        r2 = frame[int(peaks[1]) : int(peaks[1]) + 32]
        phi = np.angle(np.sum(r2 * np.conj(r1)))
        cfo_norm = phi / (2 * np.pi * 32)
        assert cfo_norm == pytest.approx(0.0, abs=1e-10)

    def test_roundtrip_with_cfo(self, ofdm, symbols):
        # Simulate cross-SDR CFO: apply a known offset within the Schmidl-Cox
        # estimable range (±1/(2*32) ≈ ±0.0156 cycles/sample) and check that
        # demodulate recovers the original symbols.
        frame = ofdm.modulate(symbols)
        cfo = 0.004  # cycles/sample — representative of ~20 ppm at 915 MHz / 1 MSPS
        n = np.arange(len(frame))
        frame_cfo = frame * np.exp(1j * 2 * np.pi * cfo * n)
        recovered = ofdm.demodulate(frame_cfo)
        np.testing.assert_allclose(recovered[:len(symbols)], symbols, atol=0.05)


# ------------------------------------------------------------------
# _correct_residual_phase
# ------------------------------------------------------------------

class TestCorrectResidualPhase:
    def test_output_length(self, ofdm, symbols):
        iframe = ofdm._construct_iframe(symbols)
        y = np.fft.fft(np.fft.ifft(iframe))
        h = ofdm._estimate_channel(y)
        eq = ofdm._equalize(y, h)
        assert len(ofdm._correct_residual_phase(eq)) == len(eq)

    def test_zero_error_on_clean_signal(self, ofdm, symbols):
        # When equalized pilots are already at 1+1j the correction is identity.
        iframe = ofdm._construct_iframe(symbols)
        y = np.fft.fft(np.fft.ifft(iframe))
        h = ofdm._estimate_channel(y)
        eq = ofdm._equalize(y, h)
        corrected = ofdm._correct_residual_phase(eq)
        np.testing.assert_allclose(corrected, eq, atol=1e-10)

    def test_removes_constant_rotation(self, ofdm, symbols):
        # Rotate the entire equalized vector by a known angle; correction must
        # remove it so that the output matches the unrotated vector.
        iframe = ofdm._construct_iframe(symbols)
        y = np.fft.fft(np.fft.ifft(iframe))
        h = ofdm._estimate_channel(y)
        eq = ofdm._equalize(y, h)
        rotation = np.exp(1j * np.pi / 5)  # 36°
        corrected = ofdm._correct_residual_phase(eq * rotation)
        np.testing.assert_allclose(corrected, eq, atol=1e-10)
