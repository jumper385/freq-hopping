from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class SyncDebug:
	"""
	Debug snapshot produced by :meth:`Modem.sync_debug`.

	Fields default to empty/zero so callers can safely read them even when
	the active modem does not override :meth:`~Modem.sync_debug`.
	"""
	corr_mag:  np.ndarray                = field(default_factory=lambda: np.array([]))
	threshold: float                     = 0.0
	peaks:     np.ndarray                = field(default_factory=lambda: np.array([], dtype=int))
	pair:      tuple[int, int] | list[tuple[int, int]] | None = None


class Modem(ABC):
	"""
	Abstract base class for all baseband communication systems.

	Subclass this and implement the three abstract members to make your modem
	drop-in compatible with ``monitor.py`` and all contract benchmarks.

	Minimal example::

		class MyModem(Modem):
			@property
			def data_tone_count(self) -> int:
				return 42

			def modulate_burst(self, symbols_matrix: np.ndarray) -> np.ndarray:
				...

			def demodulate_burst(self, y: np.ndarray, n_symbols: int) -> np.ndarray:
				...
	"""

	# ------------------------------------------------------------------
	# Abstract interface — must be implemented
	# ------------------------------------------------------------------

	@property
	@abstractmethod
	def data_tone_count(self) -> int:
		"""Number of data subcarriers (pilots excluded) per OFDM symbol."""

	@abstractmethod
	def modulate_burst(self, symbols_matrix: np.ndarray) -> np.ndarray:
		"""
		Pack *n_symbols* rows of complex data into a single time-domain burst.

		Parameters
		----------
		symbols_matrix : ndarray, complex, shape (n_symbols, data_tone_count)

		Returns
		-------
		ndarray, complex
			Time-domain baseband burst ready for transmission.
		"""

	@abstractmethod
	def demodulate_burst(self, y: np.ndarray, n_symbols: int) -> np.ndarray:
		"""
		Recover data symbols from a received burst.

		Parameters
		----------
		y : ndarray, complex
			Received baseband samples.
		n_symbols : int
			Number of OFDM symbols expected in the burst.

		Returns
		-------
		ndarray, complex, shape (n_symbols, data_tone_count)
		"""

	# ------------------------------------------------------------------
	# Optional override — sync/debug instrumentation
	# ------------------------------------------------------------------

	def sync_debug(self, y: np.ndarray) -> SyncDebug:
		"""
		Return synchronisation debug data for the given received buffer.

		The default implementation returns an empty :class:`SyncDebug`,
		which causes ``monitor.py`` to skip the correlation and marker
		overlay gracefully.  Override this to expose your modem's internal
		sync state to the live monitor.

		Parameters
		----------
		y : ndarray, complex
			Received baseband samples (same buffer passed to
			:meth:`demodulate_burst`).

		Returns
		-------
		SyncDebug
		"""
		return SyncDebug()
