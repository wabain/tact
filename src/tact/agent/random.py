from __future__ import annotations

import random
from typing import Optional

from . import BaseAgent
from ..game_model import GameModel, Move, Player


__author__ = "William Bain"
__copyright__ = "William Bain"
__license__ = "mit"


class RandomAgent (BaseAgent):
    """An agent which picks a random move"""
    def __init__(self, player):
        self._player = player

    @property
    def player(self) -> Player:
        return self._player

    def choose_move(self,
                    game: GameModel,
                    opponent_move: Optional[Move]) -> Move:
        options = []

        for x in range(game.squares):
            for y in range(game.squares):
                if game.board[x][y] is None:
                    options.append((x, y))

        assert options, 'Player invoked with no legal moves'

        return Move(player=self.player, coords=random.choice(options))
