import numpy as np

def zc(length: int, root: int = 1) -> np.ndarray:
    """Generate a Zadoff-Chu sequence of given length and root index."""
    n = np.arange(length)
    return np.exp(-1j * np.pi * root * n * (n + 1) / length)

def zc_correlation(y: np.ndarray, preamble: np.ndarray) -> np.ndarray:
    """Compute the correlation of the received signal with the given ZC preamble."""
    corr = np.correlate(y, preamble, mode='valid')
    # shift the correlation so that the peak corresponding to the first sample of the preamble is at index 0
    return np.abs(corr)

class AdaptiveThreshold:
    """
    takes an update and computes a threshold as mean + std_multiplier * std, where mean and std are updated with each new data batch. This is used to set the detection threshold for the ZC correlation peaks in monitor.py.
    """
    def __init__(self, std_multiplier: float = 4.0):
        self.std_multiplier = float(std_multiplier)
        self.mean = float(0.0)
        self.std = float(1.0)

    def update(self, data: np.ndarray):
        self.mean = np.mean(data)
        self.std = np.std(data)

    def compute_threshold(self) -> float:
        return float(self.mean + self.std_multiplier * self.std)

class schmidlecox()