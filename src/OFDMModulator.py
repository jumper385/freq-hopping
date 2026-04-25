import numpy as np

class OFDMModulator:
    def __init__(self, n_tones, cp_len=128, pilot_bins=None, pilot_val=1+0j):
        self.n_tones = n_tones
        self.gain = 2 ** 14
        self.cp_len = cp_len
        self.pilot_val = pilot_val
        # Pilots flanking data bins (100-109) + sparse coverage across spectrum
        if pilot_bins is None:
            self.pilot_bins = [50, 98, 111, 200, 350, 500, 650, 800, 950]
        else:
            self.pilot_bins = list(pilot_bins)

    def modulate(self, x_amps):
        symbol = self.gen_symbol(x_amps)          # (n_tones,) complex
        cp = symbol[-self.cp_len:]                 # cyclic prefix = last cp_len samples
        symbol_with_cp = np.concatenate([cp, symbol])
        sf = np.max(np.abs(symbol_with_cp))
        return (symbol_with_cp / sf * self.gain).reshape(-1, 1)

    def gen_symbol(self, x_amps):
        """
        Place x_amps into frequency bins starting at bin 100,
        insert pilot at pilot_bin, then IFFT to get time-domain symbol.
        Returns 1D complex array of length n_tones.
        """
        if x_amps.shape[0] > self.n_tones - 100:
            raise ValueError("Maximum number of symbols reached")

        x = np.zeros(self.n_tones, dtype=complex)

        # Insert data tones starting at bin 100
        x[100:x_amps.shape[0] + 100] = x_amps.reshape(-1)

        # Insert pilot tones for per-subcarrier equalization
        for pb in self.pilot_bins:
            x[pb] = self.pilot_val

        symbol = np.fft.ifft(x)
        return symbol

    def demod(self, x):
        x = x.reshape(-1)
        x_stripped = x[self.cp_len: self.cp_len + self.n_tones]
        fft = np.fft.fft(x_stripped)

        # Per-subcarrier channel equalization via pilot interpolation
        bins = np.array(self.pilot_bins)
        h_at_pilots = fft[bins] / self.pilot_val
        all_bins = np.arange(self.n_tones)
        mag_interp = np.interp(all_bins, bins, np.abs(h_at_pilots))
        phase_interp = np.interp(all_bins, bins, np.unwrap(np.angle(h_at_pilots)))
        h_interp = mag_interp * np.exp(1j * phase_interp)
        valid = np.abs(h_interp) > 1e-10
        fft[valid] /= h_interp[valid]

        # Zero out pilot bins
        fft[bins] = 0

        return fft