"""Built-in game runner classes"""

from __future__ import annotations

import sys
import asyncio
from abc import ABC, abstractmethod
from typing import Generator, NewType, List, Tuple, Optional

from .game_model import GameModel, GameStatus, Move, Player, get_opponent
from .agent import AbstractAgent

__author__ = "William Bain"
__copyright__ = "William Bain"
__license__ = "mit"


def launch_game(runner: AbstractGameRunner,
                agents: List[AbstractAgent],
                loop: Optional[asyncio.AbstractEventLoop] = None) -> GameStatus:
    """Utility function to run a game with the given locally-defined agents"""
    if loop is None:
        loop = asyncio.get_event_loop()

    return loop.run_until_complete(launch_game_async(runner, agents))


async def launch_game_async(runner: AbstractGameRunner,
                            agents: List[AbstractAgent]) -> GameStatus:
    for agent in agents:
        await runner.claim_player(agent.player)

    await runner.launch()
    await asyncio.gather(*(_run_agent(runner, agent) for agent in agents))
    return runner.game.status()


async def _run_agent(runner: AbstractGameRunner, agent: AbstractAgent):
    if agent.player == 1:
        move = agent.choose_move(runner.game.copy(), opponent_move=None)
        status = await runner.send_move(move)

        if status != GameStatus.Ongoing:
            return

    while True:
        opponent_move, game = await runner.opposing_move(agent.player)
        if game.status() != GameStatus.Ongoing:
            break

        move = agent.choose_move(runner.game.copy(), opponent_move)
        status = await runner.send_move(move)

        # runner.game.dump_board()

        if status != GameStatus.Ongoing:
            return


class AbstractGameRunner (ABC):
    """Abstract class for game runners.

    Subclasses must implement primitives related to negotiating game setup
    as well as functions to perform a new move and to wait on the completion
    of the opponent's move.
    """
    @abstractmethod
    async def claim_player(self, player: Player):
        """Add locally defined agents to handle interactions for a given player"""
        raise NotImplementedError('add_agent')

    @abstractmethod
    async def launch(self):
        """Launch the game with the currently defined agents.

        The game runner is responsible for determining that the agents
        needed to play the game have been registered when the task resolves.
        """
        raise NotImplementedError('launch')

    @abstractmethod
    async def send_move(self, move: Move) -> GameStatus:
        raise NotImplementedError('send_move')

    @abstractmethod
    async def opposing_move(self) -> (Move, GameModel):
        raise NotImplementedError('opposing_move')


class InMemoryGameRunner (AbstractGameRunner):
    """A simple runner implementation which maintains the game locally."""
    def __init__(self, *, squares: int, target_len: int):
        self._claimed_players = set()
        self._launched = False

        self.game = GameModel(squares=squares, target_len=target_len)
        self._pending = []
        self.last_move = None

    async def claim_player(self, player: Player):
        if player in self._claimed_players:
            raise RuntimeError(f'Duplicate claims for player {player}')

        self._claimed_players.add(player)

    async def launch(self):
        if self._claimed_players != {1, 2}:
            raise RuntimeError('Cannot launch in-memory game without all players claimed')

        if self._launched:
            raise RuntimeError('Game already launched')

        self._launched = True

    async def send_move(self, move: Move) -> GameStatus:
        if not self._launched:
            raise RuntimeError('Move requested before game launched')

        self.game.apply_move(move)
        status = self.game.status()

        pending = self._pending[:]
        del self._pending[:]

        for (expected_player, future) in pending:
            if expected_player != move.player:
                raise RuntimeError(
                    f'pending move player expected {expected_player}, but a '
                    f'legal move by {move.player} was received',
                )
            future.set_result(move)

        self.last_move = move

        return status

    async def opposing_move(self, player: Player) -> (Move, GameModel):
        if not self._launched:
            raise RuntimeError('Wait for opposing move requested before game launched')

        opponent = get_opponent(player)

        if self.last_move and self.last_move.player == opponent:
            return self.last_move, self.game.copy()

        future = asyncio.Future()
        self._pending.append((opponent, future))
        move = await future
        return move, self.game.copy()