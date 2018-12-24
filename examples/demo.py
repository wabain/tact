"""
Demo gameplay with random moves
"""
from __future__ import annotations
import argparse

from tact.game_runner import launch_game, InMemoryGameRunner
from tact.agent.random import RandomAgent


parser = argparse.ArgumentParser('demo')
parser.add_argument('--squares', type=int, default=8)
parser.add_argument('--winning-length', type=int, default=5, dest='target_len')
parser.add_argument('-v', '--verbose', action='store_true')

args = parser.parse_args()

print('Launching a local game using two random agents')

runner = InMemoryGameRunner(squares=args.squares, target_len=args.target_len)
launch_game(
    runner,
    agents=[
        RandomAgent(player=1),
        RandomAgent(player=2),
    ],
    verbose=args.verbose,
)

if not args.verbose:
    runner.game.dump_board()

print('Result:', runner.game.status().name)
