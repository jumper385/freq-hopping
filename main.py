import numpy as np
import matplotlib.pyplot as plt

from src.OFDM import OFDM
from src.PlutoSDR import PlutoSDR

def main():
    ofdm = OFDM()

    # two radios: USB-attached TX, IP-attached RX
    #rx_sdr = PlutoSDR(uri="usb:", tx_gain=-20)
    tx_sdr = PlutoSDR(uri="ip:192.168.8.93", rx_gain=30)
    rx_sdr = PlutoSDR(uri="ip:192.168.8.93", rx_gain=30)

    # build a test payload and modulate
    symbols = np.array([1 + 1j, 0 - 1j, 1.0 + 0j, 0 + 0.5j])
    frame = ofdm.modulate(symbols)

    print(f"Transmitting {len(frame)} samples ...")
    tx_sdr.transmit(frame)

    print("Receiving ...")
    y = rx_sdr.receive()

    tx_sdr.stop_transmit()

    plt.plot(y.real, label="I")
    plt.plot(y.imag, label="Q")
    plt.legend()
    plt.show()

    recovered = ofdm.demodulate(y)
    print("Recovered symbols (first 4):", recovered[:4])


if __name__ == "__main__":
    main()
