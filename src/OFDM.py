import numpy as np


class OFDM:
	"""
	OFDM modem with Zadoff-Chu preamble, pilot-based channel estimation, and CFO correction.

	Frame structure (samples):
		[silence(32)] [preamble(32)] [preamble(32)] [OFDM symbol] [silence(32)]

	Subcarrier layout (n_tones + 16 total bins):
		[guard(8)] [pilots + data (n_tones)] [guard(8)]

	Pilots are placed at every 8th subcarrier within the active region and
	transmitted with the known value ``1+1j``.
	"""

	def __init__(self, n_tones: int = 100):
		"""
		Parameters
		----------
		n_tones : int
			Number of active subcarriers (pilots + data), excluding guard bands.
		"""
		self.n_tones = n_tones

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	def modulate(self, symbols: np.ndarray) -> np.ndarray:
		"""
		Modulate complex symbols into a time-domain OFDM frame.

		Parameters
		----------
		symbols : ndarray, complex
			Data symbols to transmit.  Length must not exceed the number of
			non-pilot subcarriers (``n_tones`` minus one pilot per 8 tones).

		Returns
		-------
		ndarray, complex
			Baseband time-domain frame of length ``32 + 32 + 32 + (n_tones+16) + 32``.
		"""
		freqs = self._construct_iframe(symbols)
		x = self._ifft(freqs)
		x /= np.max(np.abs(x))
		preamble = self._generate_preamble()
		silence = np.zeros(32, dtype=complex)
		return np.concatenate([silence, preamble, preamble, x, silence])

	def demodulate(self, y: np.ndarray) -> np.ndarray:
		"""
		Demodulate a received OFDM frame back to complex data symbols.

		Performs CFO correction, strips the frame header, applies an FFT,
		equalizes via interpolated pilot estimates, and returns the
		non-pilot data subcarriers.

		Parameters
		----------
		y : ndarray, complex
			Received baseband time-domain frame.

		Returns
		-------
		ndarray, complex
			Recovered complex data symbols (pilots removed).
		"""
		y_cfo = self._cancel_cfo(y)

		# locate the OFDM symbol inside the (possibly large) receive buffer
		symbol_len = self.n_tones + 16
		peaks = self._preamble_detect(y_cfo)
		if len(peaks) >= 1:
			# data starts one preamble-length past the first detected peak
			frame_start = int(peaks[0]) + 32 + 32
		else:
			# fall back: assume y is exactly one frame
			frame_start = 32 + 32 + 32
		y_stripped = y_cfo[frame_start : frame_start + symbol_len]

		freqs = np.fft.fft(y_stripped)
		h = self._estimate_channel(freqs)
		freqs = self._equalize(freqs, h)

		pilot_mask = np.zeros(self.n_tones, dtype=bool)
		pilot_mask[::8] = True
		non_guard = freqs[8:-8]
		return non_guard[~pilot_mask]

	# ------------------------------------------------------------------
	# Private – modulation helpers
	# ------------------------------------------------------------------

	def _construct_iframe(self, x: np.ndarray) -> np.ndarray:
		"""
		Map data symbols onto the subcarrier grid with pilots and guard bands.

		Pilot subcarriers are placed at every 8th index within the active region
		and set to ``1+1j``.  Data symbols fill the remaining subcarriers
		(zero-padded when fewer symbols than slots are provided).  8-bin DC and
		high-frequency guard bands flank the active region.

		Parameters
		----------
		x : ndarray, complex
			Data symbols to place on non-pilot subcarriers.

		Returns
		-------
		ndarray, complex
			Full subcarrier vector of length ``n_tones + 16``.

		Raises
		------
		ValueError
			If ``len(x)`` exceeds the number of available data subcarriers.
		"""
		pilot_tones = np.zeros(self.n_tones, dtype=complex)
		pilot_mask = np.zeros(self.n_tones, dtype=bool)
		pilot_mask[::8] = True
		pilot_tones[pilot_mask] = 1 + 1j

		data_len = np.count_nonzero(~pilot_mask)
		if x.shape[0] > data_len:
			raise ValueError(
				f"Too many symbols ({x.shape[0]}) for available data tones ({data_len})"
			)
		zero_pad = np.zeros(data_len - x.shape[0], dtype=complex)
		pilot_tones[~pilot_mask] = np.concatenate([x, zero_pad])

		guard = np.zeros(8, dtype=complex)
		return np.concatenate([guard, pilot_tones, guard])

	def _ifft(self, x: np.ndarray) -> np.ndarray:
		"""Return the IFFT of *x* (wraps ``np.fft.ifft``)."""
		return np.fft.ifft(x)

	def _add_cp(self, x: np.ndarray, cp_len: int = 16) -> np.ndarray:
		"""
		Prepend a cyclic prefix of length *cp_len* to an OFDM symbol.

		Parameters
		----------
		x : ndarray
			Time-domain OFDM symbol.
		cp_len : int
			Number of samples to copy from the tail of *x*.

		Returns
		-------
		ndarray
			Symbol with cyclic prefix prepended, length ``len(x) + cp_len``.
		"""
		return np.concatenate([x[-cp_len:], x])

	def _generate_preamble(self, u: int = 31, n: int = 32) -> np.ndarray:
		"""
		Generate a Zadoff-Chu sequence used as the synchronisation preamble.

		The ZC property gives near-zero auto-correlation for all non-zero lags,
		making it suitable for precise timing detection and CFO estimation.

		Parameters
		----------
		u : int
			ZC root index (must be coprime with *n*).
		n : int
			Sequence length in samples.

		Returns
		-------
		ndarray, complex
			Unit-magnitude ZC sequence of length *n*.
		"""
		k = np.arange(n)
		return np.exp(-1j * np.pi * u * k * (k + 1) / n)

	# ------------------------------------------------------------------
	# Private – demodulation helpers
	# ------------------------------------------------------------------

	def _preamble_detect(self, y: np.ndarray) -> np.ndarray:
		"""
		Locate preamble occurrences via cross-correlation with an adaptive threshold.

		The threshold is set at ``mean(|corr|) + 5 * std(|corr|)`` to suppress
		side-lobes while reliably detecting the main correlation peaks.

		Parameters
		----------
		y : ndarray, complex
			Received signal to search.

		Returns
		-------
		ndarray of int
			Sample indices where the correlation magnitude exceeds the threshold.
		"""
		preamble = self._generate_preamble()
		corr = np.correlate(y, preamble, mode='valid')
		threshold = np.mean(np.abs(corr)) + 5 * np.std(np.abs(corr))
		return np.where(np.abs(corr) > threshold)[0]

	def _estimate_channel(self, y_freq: np.ndarray) -> np.ndarray:
		"""
		Estimate the channel response at every subcarrier via LS pilot extraction
		and linear interpolation.

		For each pilot subcarrier the least-squares channel estimate is:

			``H[k] = Y[k] / X[k]``

		where ``X[k] = 1+1j`` is the known transmitted pilot value.  The estimate
		is then linearly interpolated across all bins by fitting real and imaginary
		parts independently (more numerically stable than magnitude/phase).
		Bins outside the outermost pilots (i.e. guard bands) are held constant at
		the nearest pilot estimate.

		Parameters
		----------
		y_freq : ndarray, complex
			FFT output of the received OFDM symbol, length ``n_tones + 16``.

		Returns
		-------
		ndarray, complex
			Estimated channel response *H* at every subcarrier bin.
		"""
		pilot_mask = np.zeros(self.n_tones, dtype=bool)
		pilot_mask[::8] = True
		# shift pilot indices by the 8-bin lower guard band
		pilot_bins = np.where(pilot_mask)[0] + 8

		# LS estimate at pilot positions
		h_pilots = y_freq[pilot_bins] / (1 + 1j)

		# interpolate real and imaginary parts separately across all bins;
		# np.interp clamps to the edge pilot values outside the pilot range
		all_bins = np.arange(len(y_freq))
		h_real = np.interp(all_bins, pilot_bins, h_pilots.real)
		h_imag = np.interp(all_bins, pilot_bins, h_pilots.imag)
		return h_real + 1j * h_imag

	def _equalize(self, y_freq: np.ndarray, h: np.ndarray) -> np.ndarray:
		"""
		Zero-forcing equalization: divide each subcarrier by its channel estimate.

		``X_hat[k] = Y[k] / H[k]``

		This inverts the channel response under the assumption that the channel
		varies slowly across subcarriers (flat or mildly frequency-selective).
		Noise enhancement at deep fades is the known trade-off.

		Parameters
		----------
		y_freq : ndarray, complex
			Received frequency-domain subcarriers.
		h : ndarray, complex
			Estimated channel response, same length as *y_freq*.

		Returns
		-------
		ndarray, complex
			Equalized subcarrier vector.
		"""
		return y_freq / h

	def _cancel_cfo(self, y: np.ndarray) -> np.ndarray:
		"""
		Estimate and correct a carrier-frequency offset using the dual preamble.

		The frame contains two back-to-back ZC preambles of length 32.  The
		sample distance between the two detected correlation peaks encodes the
		fractional CFO as::

			cfo = 1 - (peak_distance / 32)

		A complex de-rotation is applied sample-by-sample to remove the offset.
		If fewer than two preamble peaks are detected the signal is returned
		unchanged.

		Parameters
		----------
		y : ndarray, complex
			Received signal, possibly with a carrier-frequency offset.

		Returns
		-------
		ndarray, complex
			CFO-corrected signal.
		"""
		peaks = self._preamble_detect(y)
		if len(peaks) < 2:
			return y

		estimated_cfo = 1 - (np.diff(peaks)[0] / 32)
		n = np.arange(len(y))
		return y * np.exp(-1j * 2 * np.pi * estimated_cfo * n)