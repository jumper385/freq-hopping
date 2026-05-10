#!/usr/bin/env python3
"""Run a first-pass MAB/FH simulation and write CSV logs."""
import argparse
import csv
from pathlib import Path

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fh.agents import EXP3Agent, RandomAgent, StaticAgent, ThompsonSamplingAgent, UCBAgent
from src.fh.env import FHEnvironment


def make_agent(name: str, n_channels: int, seed: int):
    if name == "random":
        return RandomAgent(n_channels, seed=seed)
    if name == "static":
        return StaticAgent(0)
    if name == "ucb":
        return UCBAgent(n_channels)
    if name == "ts":
        return ThompsonSamplingAgent(n_channels, seed=seed)
    if name == "exp3":
        return EXP3Agent(n_channels, seed=seed)
    raise ValueError(name)


def run(agent_name: str, args):
    env = FHEnvironment(n_channels=args.channels, jammer=args.jammer, seed=args.seed)
    agent = make_agent(agent_name, args.channels, args.seed)
    rows = []
    cumulative_reward = 0.0
    cumulative_regret = 0.0
    for _ in range(args.steps):
        oracle = env.oracle_reward()
        action = agent.select()
        reward, info = env.step(action)
        agent.update(action, reward)
        cumulative_reward += reward
        cumulative_regret += oracle - reward
        rows.append({
            "agent": agent_name,
            "t": info["t"],
            "action": action,
            "jammed": info["jammed"],
            "reward": reward,
            "oracle_reward": oracle,
            "cumulative_reward": cumulative_reward,
            "cumulative_regret": cumulative_regret,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", nargs="+", default=["static", "random", "ucb", "ts", "exp3"])
    parser.add_argument("--channels", type=int, default=8)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--jammer", choices=["none", "fixed", "sweep", "random", "reactive"], default="sweep")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default="results/mab_sim.csv")
    args = parser.parse_args()

    rows = []
    for agent in args.agents:
        rows.extend(run(agent, args))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    for agent in args.agents:
        final = [r for r in rows if r["agent"] == agent][-1]
        print(f"{agent:>6}: reward={final['cumulative_reward']:.1f}, regret={final['cumulative_regret']:.1f}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
