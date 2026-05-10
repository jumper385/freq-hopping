"""Small multi-armed-bandit agents for frequency-hopping experiments."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


class BanditAgent:
    """Common interface for channel-selection agents."""

    def select(self) -> int:
        raise NotImplementedError

    def update(self, arm: int, reward: float) -> None:
        raise NotImplementedError


@dataclass
class RandomAgent(BanditAgent):
    n_arms: int
    seed: int | None = None

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)

    def select(self) -> int:
        return int(self.rng.integers(self.n_arms))

    def update(self, arm: int, reward: float) -> None:
        return None


@dataclass
class StaticAgent(BanditAgent):
    arm: int = 0

    def select(self) -> int:
        return int(self.arm)

    def update(self, arm: int, reward: float) -> None:
        return None


@dataclass
class UCBAgent(BanditAgent):
    n_arms: int
    c: float = 2.0

    def __post_init__(self) -> None:
        self.t = 0
        self.counts = np.zeros(self.n_arms, dtype=int)
        self.values = np.zeros(self.n_arms, dtype=float)

    def select(self) -> int:
        untried = np.where(self.counts == 0)[0]
        if len(untried):
            return int(untried[0])
        bonus = self.c * np.sqrt(np.log(self.t + 1) / self.counts)
        return int(np.argmax(self.values + bonus))

    def update(self, arm: int, reward: float) -> None:
        self.t += 1
        self.counts[arm] += 1
        n = self.counts[arm]
        self.values[arm] += (reward - self.values[arm]) / n


@dataclass
class ThompsonSamplingAgent(BanditAgent):
    n_arms: int
    seed: int | None = None

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self.alpha = np.ones(self.n_arms, dtype=float)
        self.beta = np.ones(self.n_arms, dtype=float)

    def select(self) -> int:
        return int(np.argmax(self.rng.beta(self.alpha, self.beta)))

    def update(self, arm: int, reward: float) -> None:
        reward = float(np.clip(reward, 0.0, 1.0))
        self.alpha[arm] += reward
        self.beta[arm] += 1.0 - reward


@dataclass
class EXP3Agent(BanditAgent):
    n_arms: int
    gamma: float = 0.07
    seed: int | None = None

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self.weights = np.ones(self.n_arms, dtype=float)
        self.probs = np.ones(self.n_arms, dtype=float) / self.n_arms

    def _refresh_probs(self) -> None:
        w_sum = float(np.sum(self.weights))
        exploit = self.weights / w_sum
        self.probs = (1.0 - self.gamma) * exploit + self.gamma / self.n_arms

    def select(self) -> int:
        self._refresh_probs()
        return int(self.rng.choice(self.n_arms, p=self.probs))

    def update(self, arm: int, reward: float) -> None:
        reward = float(np.clip(reward, 0.0, 1.0))
        x_hat = reward / max(self.probs[arm], 1e-12)
        self.weights[arm] *= np.exp((self.gamma * x_hat) / self.n_arms)
