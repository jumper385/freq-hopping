import adi
import numpy as np
import matplotlib.pyplot as plt 

class PlutoSDR:
    def __init__(self, uri, fs=2_000_000):
        self.uri = uri
        self.fs = fs
        self.data_len = 1000

        self.sdr = adi.Pluto(uri)
        self.sdr.sample_rate = int(fs)
        self.sdr.tx_lo = 915000000
        self.sdr.rx_lo = 915000000
        self.sdr.gain_control_mode_chan0 = "manual"
        self.sdr.tx_hardwaregain_chan0 = -30
        self.sdr.rx_hardwaregain_chan0 = 30
        self.sdr.rx_buffer_size = 4000
        self.sdr.tx_cyclic_buffer = True

        self.pre_u = 31
        self.pre_n = 32

    def raw_transmit(self, data):
        self.sdr.tx_destroy_buffer()
        self.sdr.tx(data)

    def transmit(self, data):
        frame = self.gen_frame(data)

        self.sdr.tx_destroy_buffer()
        self.sdr.tx(frame)

    def stop_tx(self):
        self.sdr.tx_destroy_buffer()

    def raw_receive(self):
        samples = None
        for _ in range(0,5):
            samples = self.sdr.rx()
        return samples

    def receive(self):
        samples = None
        for _ in range(0,5):
            samples = self.sdr.rx()

        symbol_starts = self.detect_symbol_starts(samples)

        raw = np.array([])
        for idx in symbol_starts:
            start = int(idx)
            end = int(idx + self.data_len) if idx + self.data_len < len(samples) else int(-1)
            print(start, end)
            raw = np.concatenate([raw, samples[start:end]])

        return raw

    def detect_symbol_starts(self, x):
        # detects all possible start symbols tarts after frame

        # detect samples
        preamble = self.gen_preamble(self.pre_u, self.pre_n)
        corr_raw = np.correlate(x, preamble, mode="same")
        corr_raw = np.abs(corr_raw)
        corr_thresh = self.determine_threshold(corr_raw)
        peak_sig = np.sign(corr_raw - corr_thresh)

        # peaks where peak_sig > 0.5
        sigs = np.where(peak_sig > 0.5)
        frame_starts = np.array(sigs) + int(self.pre_n / 2)
    
        return frame_starts.reshape(-1)

    def determine_threshold(self, x, mul = 5):
        mean = np.mean(x)
        std = np.std(x)
        thresh = mean + std * mul
        return thresh

    def gen_frame(self, data, silence_len=32):
        # silence + preamble + data + silence
        zc_preamble = self.gen_preamble(u = self.pre_u, N = self.pre_n)
        silence = np.zeros(silence_len)

        data_max = np.max(np.abs(data))
        zc_preamble *= data_max # assumes zc max amp = 1

        frame = np.concatenate([silence, zc_preamble, data, silence])
        return frame

    def gen_preamble(self, u=3, N=31):
        if u > N:
            raise ValueError(f"cz root idx {u} must be smaller than seq_len {seq_len}")
        n = np.arange(0, N)
        zc =  np.exp( -1j * (np.pi * u * n**2)/N)
        return zc
