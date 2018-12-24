import random
import pytest

from tact.game_runner import launch_game, InMemoryGameRunner
from tact.agent.random import RandomAgent


__author__ = "William Bain"
__copyright__ = "William Bain"
__license__ = "mit"


def test_random_run():
    """Run a game with two random agents and make sure... nothing bad happens"""
    # TODO: set a seed

    runner = InMemoryGameRunner(squares=8, target_len=5)
    launch_game(runner, agents=[
        RandomAgent(player=1),
        RandomAgent(player=2),
    ])

