"""
Demo gameplay with random moves
"""
from __future__ import annotations

from tact.game_runner import launch_game, InMemoryGameRunner
from tact.agent.random import RandomAgent


print('Launching a local game using two random agents')

runner = InMemoryGameRunner(squares=8, target_len=5)
launch_game(runner, agents=[
    RandomAgent(player=1),
    RandomAgent(player=2),
])

runner.game.dump_board()
print('Result:', runner.game.status().name)
