import numpy as np
import matplotlib.pyplot as plt

class OFDMModulator:
    def __init__(self,n_tones):
        self.n_tones = n_tones
        self.gain = 2 ** 14

    def modulate(self, x_amps, cp_len=32):
        symbol = self.gen_symbol(x_amps).reshape(-1)
        cp = symbol[-cp_len:]                     # last cp_len samples
        symbol_with_cp = np.concatenate([cp, symbol])
        sf = np.max(np.abs(symbol_with_cp))
        return (symbol_with_cp / sf * self.gain).reshape(-1, 1)

    def demod(self, x, cp_len=32):
        x = x.reshape(-1)[cp_len:cp_len + self.n_tones]  # strip CP, take exactly n_tones samples
        return np.fft.fft(x)
    
    def gen_symbol(self, x_amps):
        """
        symbol = [...n_tones]; amplitude of each tone
        out => ifft of symbol
        """

        x = np.zeros(self.n_tones).reshape(-1,1)

        if x_amps.shape[0] > self.n_tones:
            raise ValueError("Maximum Number of Symbols Reached")

        x[100:x_amps.shape[0]+100] = x_amps
        x = x.reshape(-1)
        symbol = np.fft.ifft(x)

        return symbol.reshape(-1,1)