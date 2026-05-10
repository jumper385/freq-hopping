import numpy as np
from dataclasses import dataclass


@dataclass
class AcquisitionMeta:
    """Structured result from OFDM.acquire()."""
    valid: bool
    p1: int | None = None
    p2: int | None = None
    peak_count: int = 0
    peak_margin: float = 0.0
    cfo_norm: float = 0.0
    reason: str = ""


class OFDM:
	"""
	OFDM modem with Zadoff-Chu preamble, pilot-based channel estimation, and CFO correction.

	Frame structure (samples):
		[silence(32)] [preamble(32)] [preamble(32)] [CP + OFDM symbol (+ CS)] [silence(32)]

	Subcarrier layout (n_tones + 16 total bins):
		[guard(8)] [pilots + data (n_tones)] [guard(8)]

	Pilots are placed at every 8th subcarrier within the active region and
	transmitted with the known value ``1+1j``.
	"""

	def __init__(self, n_tones: int = 50, cp_len: int = 16, roll_off: int = 0):
		"""
		Parameters
		----------
		n_tones : int
			Number of active subcarriers (pilots + data), excluding guard bands.
		cp_len : int
			Cyclic prefix length in samples.  Must exceed the maximum expected
			multipath delay spread to maintain inter-symbol orthogonality.
		roll_off : int
			Raised-cosine window roll-off length in samples.  When non-zero a
			cyclic suffix of length *roll_off* is appended and a raised-cosine
			taper is applied across the CP/CS edges to reduce out-of-band
			emissions.  Set to ``0`` (default) to disable windowing.
		"""
		self.n_tones = n_tones
		self.cp_len = cp_len
		self.roll_off = roll_off

	# ------------------------------------------------------------------
	# Public API – link budget / throughput helpers
	# ------------------------------------------------------------------

	@property
	def fft_len(self) -> int:
		"""FFT length in samples/bins, including active tones and guard bands."""
		return self.n_tones + 16

	@property
	def data_tone_count(self) -> int:
		"""Number of payload-carrying tones after pilot removal."""
		pilot_mask = np.zeros(self.n_tones, dtype=bool)
		pilot_mask[::8] = True
		return int(np.count_nonzero(~pilot_mask))

	@property
	def symbol_block_len(self) -> int:
		"""Samples per CP-prefixed OFDM data symbol, excluding preambles/silence."""
		return self.fft_len + self.cp_len + self.roll_off

	@property
	def sync_overhead_len(self) -> int:
		"""Samples consumed by leading silence, dual preamble, and trailing silence."""
		return 32 + 32 + 32 + 32

	def frame_len(self, n_symbols: int = 1) -> int:
		"""Total samples in a single-frame/burst containing *n_symbols* OFDM symbols."""
		if n_symbols < 1:
			raise ValueError("n_symbols must be >= 1")
		return self.sync_overhead_len + n_symbols * self.symbol_block_len

	def payload_bits_per_frame(self, bits_per_symbol: int = 2, n_symbols: int = 1) -> int:
		"""Payload bits carried by one frame/burst for a given constellation order."""
		if bits_per_symbol < 1:
			raise ValueError("bits_per_symbol must be >= 1")
		if n_symbols < 1:
			raise ValueError("n_symbols must be >= 1")
		return self.data_tone_count * bits_per_symbol * n_symbols

	def theoretical_throughput_bps(
		self,
		sample_rate: float = 1_000_000,
		bits_per_symbol: int = 2,
		n_symbols: int = 1,
	) -> float:
		"""
		Return ideal payload throughput for the baseband frame format.

		This is a framing-only metric: it assumes every payload symbol is decoded
		correctly and does not include SDR retune latency, stale-buffer flushing,
		Python loop overhead, packet erasures, retransmission, or FEC overhead.
		"""
		if sample_rate <= 0:
			raise ValueError("sample_rate must be > 0")
		return self.payload_bits_per_frame(bits_per_symbol, n_symbols) * sample_rate / self.frame_len(n_symbols)

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
			Baseband time-domain frame of length
			``32 + 32 + 32 + (n_tones + 16 + cp_len + roll_off) + 32``.
		"""
		freqs = self._construct_iframe(symbols)
		x = self._ifft(freqs)
		x /= np.max(np.abs(x))
		x = self._add_cp(x, self.cp_len)
		if self.roll_off > 0:
			x = self._apply_window(x)
		preamble = self._generate_preamble()
		silence = np.zeros(32, dtype=complex)
		return np.concatenate([silence, preamble, preamble, x, silence])

	def demodulate(self, y: np.ndarray) -> np.ndarray:
		"""
		Demodulate a received OFDM frame back to complex data symbols.

		Performs CFO correction, strips the frame header, removes the cyclic
		prefix, applies an FFT, equalizes via LMMSE using interpolated pilot
		channel estimates and guard-band noise variance, and returns the
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

		# locate the CP+symbol block inside the (possibly large) receive buffer
		symbol_len = self.n_tones + 16 + self.cp_len + self.roll_off
		peaks = self._preamble_detect(y_cfo)
		pair = self._find_preamble_pair(peaks)
		if pair is not None:
			# Valid P1+P2 pair found: anchor on P2.
			frame_start = pair[1] + 32
		elif len(peaks) == 1:
			# Only one peak detected; assume it is P1.
			frame_start = int(peaks[0]) + 32 + 32
		else:
			# fall back: assume y is exactly one frame
			frame_start = 32 + 32 + 32
		y_stripped = y_cfo[frame_start : frame_start + symbol_len]
		y_sym = self._remove_cp(y_stripped)

		freqs = np.fft.fft(y_sym)
		noise_var = self._estimate_noise_var(freqs)
		h = self._estimate_channel(freqs)
		freqs = self._equalize(freqs, h, noise_var)
		freqs = self._correct_residual_phase(freqs)

		pilot_mask = np.zeros(self.n_tones, dtype=bool)
		pilot_mask[::8] = True
		non_guard = freqs[8:-8]
		return non_guard[~pilot_mask]

	def modulate_burst(self, symbols_matrix: np.ndarray) -> np.ndarray:
		"""
		Modulate multiple OFDM symbols into a single burst frame.

		One preamble pair is transmitted at the head of the burst; all data
		symbols follow back-to-back, each with its own cyclic prefix (and
		optional cyclic suffix when ``roll_off > 0``).

		Parameters
		----------
		symbols_matrix : ndarray, complex, shape (n_syms, data_tones)
			Data symbols for each OFDM symbol.  Each row is passed to
			``_construct_iframe`` independently.

		Returns
		-------
		ndarray, complex
			Burst frame: ``[silence | preamble | preamble | sym_0 | sym_1 |
			... | sym_{n-1} | silence]``.
		"""
		blocks = []
		for row in symbols_matrix:
			freqs = self._construct_iframe(row)
			x = self._ifft(freqs)
			x_cp = self._add_cp(x, self.cp_len)
			if self.roll_off > 0:
				x_cp = self._apply_window(x_cp)
			blocks.append(x_cp)

		burst_body = np.concatenate(blocks)
		peak = np.max(np.abs(burst_body))
		if peak > 0:
			burst_body /= peak

		preamble = self._generate_preamble()
		silence = np.zeros(32, dtype=complex)
		return np.concatenate([silence, preamble, preamble, burst_body, silence])

	def demodulate_burst(self, y: np.ndarray, n_symbols: int) -> np.ndarray:
		"""
		Demodulate a burst frame that contains *n_symbols* OFDM symbols.

		CFO correction and timing recovery use the same preamble-based logic
		as ``demodulate``.  Each OFDM symbol is then processed independently:
		CP removal → FFT → noise-variance estimation → LMMSE equalization →
		residual-phase correction.

		Parameters
		----------
		y : ndarray, complex
			Received burst frame.
		n_symbols : int
			Number of OFDM symbols in the burst.

		Returns
		-------
		ndarray, complex, shape (n_symbols, data_tones)
			Recovered data symbols, one row per OFDM symbol.
		"""
		y_cfo = self._cancel_cfo(y)
		symbol_len = self.n_tones + 16 + self.cp_len + self.roll_off

		peaks = self._preamble_detect(y_cfo)
		pair = self._find_preamble_pair(peaks)
		if pair is not None:
			frame_start = pair[1] + 32
		elif len(peaks) == 1:
			frame_start = int(peaks[0]) + 32 + 32
		else:
			frame_start = 32 + 32 + 32

		pilot_mask = np.zeros(self.n_tones, dtype=bool)
		pilot_mask[::8] = True

		results = []
		for i in range(n_symbols):
			start = frame_start + i * symbol_len
			y_sym = self._remove_cp(y_cfo[start : start + symbol_len])
			freqs = np.fft.fft(y_sym)
			noise_var = self._estimate_noise_var(freqs)
			h = self._estimate_channel(freqs)
			freqs = self._equalize(freqs, h, noise_var)
			freqs = self._correct_residual_phase(freqs)
			results.append(freqs[8:-8][~pilot_mask])

		return np.array(results)

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

	def _remove_cp(self, x: np.ndarray) -> np.ndarray:
		"""
		Strip the cyclic prefix (and cyclic suffix when *roll_off* > 0).

		Returns the ``n_tones + 16`` sample OFDM body that is passed to the FFT.

		Parameters
		----------
		x : ndarray
			Received block of length ``cp_len + (n_tones + 16) + roll_off``.

		Returns
		-------
		ndarray
			OFDM symbol body, length ``n_tones + 16``.
		"""
		if self.roll_off > 0:
			return x[self.cp_len : -self.roll_off]
		return x[self.cp_len:]

	def _apply_window(self, x: np.ndarray) -> np.ndarray:
		"""
		Append a cyclic suffix and apply a raised-cosine taper to reduce OOB.

		The input *x* is ``[CP | symbol]``.  A cyclic suffix (CS) of length
		``roll_off`` — a copy of the first ``roll_off`` samples of the symbol
		body — is appended.  A raised-cosine ramp is then applied to the
		leading ``roll_off`` samples of the CP and the trailing ``roll_off``
		samples of the CS.  The symbol body (the FFT window at the receiver)
		remains unmodified (window = 1), so orthogonality is preserved.

		Parameters
		----------
		x : ndarray
			CP-prefixed symbol, length ``cp_len + n_tones + 16``.

		Returns
		-------
		ndarray
			Windowed block, length ``cp_len + n_tones + 16 + roll_off``.
		"""
		symbol_body = x[self.cp_len:]
		cs = symbol_body[:self.roll_off]
		x_ext = np.concatenate([x, cs])

		t = np.arange(self.roll_off) / self.roll_off
		ramp_up = 0.5 * (1 - np.cos(np.pi * t))
		window = np.ones(len(x_ext))
		window[:self.roll_off] = ramp_up
		window[-self.roll_off:] = ramp_up[::-1]
		return x_ext * window

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

	def _correlate(self, y: np.ndarray) -> tuple[np.ndarray, float]:
		"""
		Cross-correlate *y* with the ZC preamble and compute the adaptive threshold.

		Separating this from ``_preamble_detect`` lets callers (e.g. a debug
		plot in ``main.py``) inspect the raw correlation magnitude and threshold
		without re-running the correlation a second time.

		Parameters
		----------
		y : ndarray, complex
			Received signal.

		Returns
		-------
		mag : ndarray of float
			Absolute correlation magnitude, length ``len(y) - 32 + 1``.
		threshold : float
			Adaptive detection threshold: ``mean(mag) + 5 * std(mag)``.
		"""
		preamble = self._generate_preamble()
		corr = np.correlate(y, preamble, mode='valid')
		mag = np.abs(corr)
		threshold = np.mean(mag) + 4 * np.std(mag)
		# threshold = 5 * np.std(mag)
		return mag, threshold

	def _preamble_detect(self, y: np.ndarray) -> np.ndarray:
		"""
		Locate preamble occurrences via rising-edge detection on an adaptive threshold.

		The adaptive threshold is ``mean(|corr|) + 5 * std(|corr|)``.  Rather
		than returning every sample above the threshold (which yields many
		indices per broad correlation peak), only the **rising-edge** sample —
		the first sample where the magnitude crosses the threshold from below —
		is returned for each peak.  This gives exactly one index per physical
		preamble occurrence, which is required for reliable P1/P2 pair matching
		in ``_find_preamble_pair``.

		Parameters
		----------
		y : ndarray, complex
			Received signal to search.

		Returns
		-------
		ndarray of int
			Rising-edge sample indices, one per preamble detection.
		"""
		mag, threshold = self._correlate(y)

		# Prepend False so a peak starting at index 0 is also captured.
		above = mag > threshold
		rising = np.where(~np.concatenate([[False], above[:-1]]) & above)[0]
		return rising

	def _find_preamble_pair(self, peaks: np.ndarray) -> tuple[int, int] | None:
		"""
		Find the first consecutive peak pair separated by approximately one
		preamble length (32 samples, ±2 sample tolerance).

		With a cyclic TX, the received buffer contains many correlation peaks.
		Blindly using ``peaks[0]`` and ``peaks[1]`` fails whenever a spurious
		peak (multipath echo, IQ-imbalance artifact, or cyclic-DMA glitch)
		appears before the true P1.  This method scans all adjacent peak pairs
		until it finds one within the P1→P2 spacing window, making timing and
		CFO estimation robust to any number of spurious peaks.

		A tolerance of ±2 samples is used because the rising-edge of a
		correlation peak varies by ±1 sample depending on noise and channel
		shape, meaning the apparent P1→P2 spacing observed from rising edges
		can differ from the nominal 32 samples by up to ~2 samples.

		Parameters
		----------
		peaks : ndarray of int
			All detected correlation peak positions, sorted ascending.

		Returns
		-------
		tuple (p1, p2) or None
			Sample indices of P1 and P2, or ``None`` if no valid pair is found.
		"""
		pairs = self._find_all_preamble_pairs(peaks)
		return pairs[0] if pairs else None

	def _find_all_preamble_pairs(self, peaks: np.ndarray) -> list[tuple[int, int]]:
		"""
		Return all consecutive peak pairs separated by approximately one
		preamble length (32 samples, ±2 sample tolerance), in scan order.

		This is used by ``acquire`` when multi‑candidate acquisition is needed:
		the first candidate may be a false lock (e.g. stale cyclic‑DMA data),
		but a later candidate in the same buffer may be a valid frame.

		Parameters
		----------
		peaks : ndarray of int
			All detected correlation peak positions, sorted ascending.

		Returns
		-------
		list of (p1, p2) tuples
			May be empty if no pair is found.
		"""
		preamble_len = 32
		tolerance = 2
		pairs = []
		for i in range(len(peaks) - 1):
			spacing = int(peaks[i + 1]) - int(peaks[i])
			if abs(spacing - preamble_len) <= tolerance:
				pairs.append((int(peaks[i]), int(peaks[i + 1])))
		return pairs

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

	def _equalize(self, y_freq: np.ndarray, h: np.ndarray, noise_var: float = 0.0) -> np.ndarray:
		"""
		LMMSE equalization per subcarrier.

		``X̂[k] = H*[k] · Y[k] / (|H[k]|² + noise_var)``

		When *noise_var* is zero this reduces to zero-forcing (``Y[k] / H[k]``).
		A non-zero noise variance regularises the matrix inversion and suppresses
		noise enhancement at subcarriers with small channel coefficients.

		Parameters
		----------
		y_freq : ndarray, complex
			Received frequency-domain subcarriers.
		h : ndarray, complex
			Estimated channel response, same length as *y_freq*.
		noise_var : float
			Per-subcarrier noise variance.  Obtain from ``_estimate_noise_var``.

		Returns
		-------
		ndarray, complex
			Equalized subcarrier vector.
		"""
		return np.conj(h) * y_freq / (np.abs(h) ** 2 + noise_var)

	def _estimate_noise_var(self, y_freq: np.ndarray) -> float:
		"""
		Estimate per-subcarrier noise variance from guard-band bins.

		Guard-band subcarriers carry no transmitted signal, so the received
		power in those bins is pure noise.  The mean power across the 16
		guard bins (8 low + 8 high) gives an unbiased estimate of ``σ²``.

		Parameters
		----------
		y_freq : ndarray, complex
			FFT output of the received OFDM symbol, length ``n_tones + 16``.

		Returns
		-------
		float
			Estimated noise variance per subcarrier.
		"""
		guard = np.concatenate([y_freq[:8], y_freq[-8:]])
		return float(np.mean(np.abs(guard) ** 2))

	def _correct_residual_phase(self, equalized: np.ndarray) -> np.ndarray:
		"""
		Remove any residual common-phase error using equalized pilot subcarriers.

		After zero-forcing equalization the pilots should ideally equal ``1+1j``.
		Any *common* rotation across all pilots (caused by residual CFO phase
		accumulated over the OFDM symbol, LO phase noise, or a constant channel
		phase) is estimated as the mean pilot phase deviation and subtracted.

		Parameters
		----------
		equalized : ndarray, complex
			Equalized frequency-domain subcarriers, length ``n_tones + 16``.

		Returns
		-------
		ndarray, complex
			Phase-corrected subcarrier vector.
		"""
		pilot_mask = np.zeros(self.n_tones, dtype=bool)
		pilot_mask[::8] = True
		# pilot positions in the full FFT vector (offset by lower guard band)
		pilot_bins = np.where(pilot_mask)[0] + 8
		pilot_ref = 1 + 1j
		phase_err = np.mean(np.angle(equalized[pilot_bins] / pilot_ref))
		return equalized * np.exp(-1j * phase_err)

	def _cancel_cfo(self, y: np.ndarray) -> np.ndarray:
		"""
		Estimate and correct a carrier-frequency offset using the dual preamble.

		The frame contains two back-to-back ZC preambles of length 32.
		Schmidl-Cox estimation: the phase of the conjugate product of the two
		received preamble windows encodes the CFO as::

			phi  = angle( sum( r2 * conj(r1) ) )
			cfo  = phi / (2 * pi * preamble_len)   [cycles/sample]

		This is unambiguous for |cfo| < 1 / (2 * preamble_len), i.e.
		±15 625 Hz at 1 MSPS with a 32-sample preamble — sufficient to cover
		the ±20 ppm LO mismatch of two independent PlutoSDRs at 915 MHz
		(≈ ±18 300 Hz).

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
		pair = self._find_preamble_pair(peaks)
		if pair is None:
			return y

		preamble_len = 32
		p1_start, p2_start = pair
		if p2_start + preamble_len > len(y):
			return y

		r1 = y[p1_start : p1_start + preamble_len]
		r2 = y[p2_start : p2_start + preamble_len]

		# Schmidl-Cox: phase of the conjugate product of the two received
		# preamble copies is proportional to the CFO.
		phi = np.angle(np.sum(r2 * np.conj(r1)))
		cfo_norm = phi / (2 * np.pi * preamble_len)   # cycles/sample

		n = np.arange(len(y))
		return y * np.exp(-1j * 2 * np.pi * cfo_norm * n)

	# ------------------------------------------------------------------
	# Public — acquisition / lock-quality gating
	# ------------------------------------------------------------------

	def acquire(self, y: np.ndarray, min_margin: float = 2.5,
	            max_cfo_norm: float | None = None) -> AcquisitionMeta:
		"""Detect preamble and return structured lock-quality metadata.

		This is the single entry‑point for deciding whether a received burst
		contains a usable OFDM frame.  The two‑stage gate first checks the
		Zadoff‑Chu correlation margin, then optionally validates the
		Schmidl‑Cox CFO estimate against an implausibility bound.

		Parameters
		----------
		y : ndarray, complex
			Received baseband signal.
		min_margin : float
			Minimum peak‑max / adaptive‑threshold ratio for the ZC stage.
		max_cfo_norm : float or None
			Maximum |CFO| in cycles/sample for the S&C sanity stage.
			``None`` disables the CFO gate.  At 1 MSPS, ``0.002`` ≈ 2000 Hz
			rejects ±15 kHz false‑lock outliers while accepting real
			±0‑1000 Hz locks across independent PlutoSDRs.

		Returns
		-------
		AcquisitionMeta
			Structured result with ``valid`` flag and diagnostic fields.
		"""
		y_cfo = self._cancel_cfo(y)
		corr_mag, threshold = self._correlate(y_cfo)
		peaks = self._preamble_detect(y_cfo)
		pair = self._find_preamble_pair(peaks)
		peak_max = float(np.max(corr_mag)) if len(corr_mag) else 0.0
		margin = peak_max / float(threshold) if threshold > 0 else 0.0

		if pair is None and len(peaks) < 1:
			return AcquisitionMeta(valid=False, peak_count=len(peaks),
			                       peak_margin=margin, reason="no peaks")
		if pair is None:
			return AcquisitionMeta(valid=False, peak_count=len(peaks),
			                       peak_margin=margin,
			                       reason=f"no P1/P2 pair ({len(peaks)} peaks)")
		if margin < min_margin:
			return AcquisitionMeta(valid=False, p1=pair[0], p2=pair[1],
			                       peak_count=len(peaks), peak_margin=margin,
			                       reason=f"low margin {margin:.2f} < {min_margin}")

		# CFO from the pair we used
		preamble_len = 32
		r1 = y_cfo[pair[0]: pair[0] + preamble_len]
		r2 = y_cfo[pair[1]: pair[1] + preamble_len]
		phi = np.angle(np.sum(r2 * np.conj(r1)))
		cfo_norm = phi / (2 * np.pi * preamble_len)

		# CFO sanity gate: reject false locks with implausible CFO
		if max_cfo_norm is not None and abs(cfo_norm) > max_cfo_norm:
			return AcquisitionMeta(valid=False, p1=pair[0], p2=pair[1],
			                       peak_count=len(peaks), peak_margin=margin,
			                       cfo_norm=cfo_norm,
			                       reason=f"CFO outlier |{cfo_norm:.6f}| > {max_cfo_norm}")

		return AcquisitionMeta(valid=True, p1=pair[0], p2=pair[1],
		                       peak_count=len(peaks), peak_margin=margin,
		                       cfo_norm=cfo_norm, reason="ok")
