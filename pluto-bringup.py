import numpy as np
import adi
import matplotlib.pyplot as plt

from src.PlutoSDR import PlutoSDR

plt.rcParams.update({
    'lines.linewidth': 1,
    'axes.prop_cycle': plt.cycler(color=['black', 'red', 'blue', 'green', 'orange', 'purple'])
})

# --- SDR setup ---
sdr1 = PlutoSDR("ip:192.168.8.93", fs=2_000_000)
sdr2 = PlutoSDR("usb:")

# --- Generate sinusoid ---
f_tone = 100e3
N = 1000
t = np.arange(N) / sdr1.fs

iq_tx = np.exp(2j * np.pi * f_tone * t)
iq_tx *= 2**14  # scale

# --- Transmit ---
sdr1.transmit(iq_tx)

# --- Receive ---
print("Sampling...")
iq_rx = sdr2.receive()

# Stop TX buffer
sdr1.stop_tx()

# --- Plot time domain ---
plt.figure()
plt.plot(np.real(iq_rx), label="I")
plt.plot(np.imag(iq_rx), label="Q")
plt.title("Received IQ (Time Domain)")
plt.legend()
plt.grid()

# --- Plot frequency domain ---
fft = np.fft.fftshift(np.fft.fft(iq_rx))
freqs = np.fft.fftshift(np.fft.fftfreq(len(fft), 1 / sdr2.fs))

plt.figure()
plt.plot(freqs / 1e3, 20 * np.log10(np.abs(fft)))
plt.title("Spectrum")
plt.xlabel("Frequency (kHz)")
plt.ylabel("Magnitude (dB)")
plt.grid()

plt.show()
