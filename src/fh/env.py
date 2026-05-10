"""Minimal FH channel environment for algorithm bring-up."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class FHEnvironment:
    """Toy channel model with controllable jammer behaviours.

    Reward is a bounded packet-success proxy in [0, 1]. It is intentionally
    lightweight: enough to validate agent interfaces before the PlutoSDR link
    supplies measured PER/SINR/ACK rewards.
    """

    n_channels: int = 8
    jammer: str = "sweep"  # none | fixed | sweep | random | reactive
    noise_floor: float = 0.02
    jam_penalty: float = 0.85
    seed: int | None = None

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self.t = 0
        self.last_action: int | None = None

    def jammed_channel(self) -> int | None:
        if self.jammer == "none":
            return None
        if self.jammer == "fixed":
            return 0
        if self.jammer == "sweep":
            return self.t % self.n_channels
        if self.jammer == "random":
            return int(self.rng.integers(self.n_channels))
        if self.jammer == "reactive":
            return self.last_action
        raise ValueError(f"unknown jammer mode: {self.jammer}")

    def oracle_reward(self) -> float:
        jammed = self.jammed_channel()
        rewards = [self._reward_for(ch, jammed) for ch in range(self.n_channels)]
        return float(max(rewards))

    def _reward_for(self, action: int, jammed: int | None) -> float:
        base = 1.0 - self.noise_floor
        if jammed is not None and action == jammed:
            base -= self.jam_penalty
        return float(np.clip(base, 0.0, 1.0))

    def step(self, action: int) -> tuple[float, dict]:
        if not 0 <= action < self.n_channels:
            raise ValueError("action out of range")
        jammed = self.jammed_channel()
        expected = self._reward_for(action, jammed)
        reward = float(np.clip(expected + self.rng.normal(0.0, self.noise_floor), 0.0, 1.0))
        info = {"t": self.t, "action": action, "jammed": jammed, "expected_reward": expected}
        self.last_action = action
        self.t += 1
        return reward, info
