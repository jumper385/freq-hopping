import matplotlib.pyplot as plt
import numpy as np
import torch
import adi

import time

import sionna.phy

SDR_IP = "ip:192.168.8.93"
from src.PlutoSDR import PlutoSDR
from src.OFDMModulator import OFDMModulator

# STEP 1: DEFINE THE BINARY SOURCE
batch_size =10 
num_bits_per_symbol = 4
binary_source = sionna.phy.mapping.BinarySource()
b = binary_source([batch_size, num_bits_per_symbol])

constellation = sionna.phy.mapping.Constellation("qam", num_bits_per_symbol)

# STEP 2: Map each row to the constellations symbols according to the bit
mapper = sionna.phy.mapping.Mapper(constellation=constellation)
x = mapper(b)

# STEP 3: Transmit accross the channel
sdr1 = PlutoSDR(uri=SDR_IP)

mod = OFDMModulator(1001)

rf = mod.out(x)

sdr1.transmit(rf)

rx_raw = sdr1.receive()[:1000].reshape(-1)
y = mod.demod(rx_raw)

no = 0.1

# STEP 4: Demap the signal after sending
demapper = sionna.phy.mapping.Demapper("maxlog", constellation=constellation)
yhat_estimates = demapper(y, no)
y_hat = (yhat_estimates > 0).float()

fig, ax = plt.subplots(4, sharex=True)
ax[0].plot(x.real)
ax[0].plot(x.imag)
ax[1].plot(y[100:-2].real, label="real")
ax[1].plot(y[100:-2].imag, label="imag")
ax[1].legend()
ax[2].plot(rf.real)
ax[2].plot(rf.imag)
ax[3].plot(rx_raw.real)
ax[3].plot(rx_raw.imag)
plt.show()

# STEP 5: Compute BLER
# bler = sionna.phy.utils.compute_bler(b, y_hat)
# print(bler)

sdr1.stop_tx()
