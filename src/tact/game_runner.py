"""Built-in game runner classes"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from asyncio import Future
from typing import Generator, NewType, List, Tuple, Optional

from .game_model import GameModel, GameStatus, Move, Player, get_opponent

__author__ = "William Bain"
__copyright__ = "William Bain"
__license__ = "mit"


class BaseGameRunner (ABC):
    """Base class for game runners.

    Subclasses must implement primitives to apply a new move and wait on the
    completion of the opponent's move.
    """
    @abstractmethod
    async def send_move(self, move: Move) -> GameStatus:
        raise NotImplementedError('send_move')

    @abstractmethod
    async def opposing_move(self) -> (Move, GameModel):
        raise NotImplementedError('opposing_move')


class InMemoryGameRunner (BaseGameRunner):
    """A simple runner implementation which maintains the game locally."""
    def __init__(self, *, squares: int, target_len: int):
        self.game = GameModel(squares=squares, target_len=target_len)
        self._pending = []
        self.last_move = None

    async def send_move(self, move: Move) -> GameStatus:
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
        opponent = get_opponent(player)

        if self.last_move and self.last_move.player == opponent:
            return self.last_move, self.game.copy()

        future = Future()
        self._pending.append((opponent, future))
        move = await future
        return move, self.game.copy()
