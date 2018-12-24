"""
Demo gameplay with random moves
"""
from __future__ import annotations
import argparse

from tact.game_runner import launch_game, InMemoryGameRunner
from tact.agent.random import RandomAgent
from tact.agent.alun import AlunAgent


parser = argparse.ArgumentParser('demo')
parser.add_argument('--squares', type=int, default=8)
parser.add_argument('--winning-length', type=int, default=5, dest='target_len')
parser.add_argument('-v', '--verbose', action='store_true')

args = parser.parse_args()

agents = [
    AlunAgent(player=1),
    RandomAgent(player=2),
]

print('Launching a local game with', type(agents[0]).__name__, 'against',
      type(agents[1]).__name__)

runner = InMemoryGameRunner(squares=args.squares, target_len=args.target_len)
game = launch_game(runner, agents=agents, verbose=args.verbose)

if not args.verbose:
    game.dump_board()

print('Result:', game.status().name)
