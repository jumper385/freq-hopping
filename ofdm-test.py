import matplotlib.pyplot as plt
import numpy as np
import adi

from src.OFDMModulator import OFDMModulator
from src.PlutoSDR import PlutoSDR

mod = OFDMModulator(1000)
sdr = PlutoSDR("ip:192.168.8.93")

x = np.array([1+1j, 0 - 1j, 1, 0 + 0.5j]).reshape(-1, 1)

rf = mod.modulate(x).reshape(-1)
sdr.transmit(rf)

rf_recv = sdr.receive()
rf_hat = mod.demod(rf_recv[:1000])

fig, ax = plt.subplots(4, sharex=True)

ax[0].set_title("Waveform to Send")
ax[0].plot(rf.real)
ax[0].plot(rf.imag)

ax[1].set_title("Received Waveform (Preamble Removed)")
ax[1].plot(rf_recv.real[:1000])
ax[1].plot(rf_recv.imag[:1000])

ax[2].set_title("Estimated FFT")
ax[2].plot(rf_hat.real[:1000])
ax[2].plot(rf_hat.imag[:1000])

x_dbg = np.zeros(1000, dtype=complex)
x_dbg[100:x.shape[0]+100] = x.reshape(-1)

ax[3].set_title("Target FFT")
ax[3].plot(x_dbg.real, label="real")
ax[3].plot(x_dbg.imag, label="imag")
ax[3].legend()

fig.tight_layout()

plt.show()
