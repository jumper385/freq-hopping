import numpy as np

from src.fh.agents import EXP3Agent, RandomAgent, StaticAgent, ThompsonSamplingAgent, UCBAgent
from src.fh.env import FHEnvironment


def test_env_reward_lower_on_jammed_channel():
    env = FHEnvironment(n_channels=4, jammer="fixed", noise_floor=0.0)
    bad, info_bad = env.step(0)
    good, info_good = env.step(1)
    assert info_bad["jammed"] == 0
    assert info_good["jammed"] == 0
    assert good > bad


def test_agents_select_valid_arms():
    agents = [
        RandomAgent(4, seed=1),
        StaticAgent(2),
        UCBAgent(4),
        ThompsonSamplingAgent(4, seed=1),
        EXP3Agent(4, seed=1),
    ]
    for agent in agents:
        arm = agent.select()
        assert 0 <= arm < 4
        agent.update(arm, 1.0)


def test_ucb_learns_best_fixed_arm():
    agent = UCBAgent(3)
    for _ in range(60):
        arm = agent.select()
        reward = 1.0 if arm == 2 else 0.0
        agent.update(arm, reward)
    assert agent.select() == 2


def test_exp3_probabilities_sum_to_one():
    agent = EXP3Agent(5, seed=1)
    arm = agent.select()
    agent.update(arm, 0.5)
    agent._refresh_probs()
    np.testing.assert_allclose(np.sum(agent.probs), 1.0)
