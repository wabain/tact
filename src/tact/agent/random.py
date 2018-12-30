from __future__ import annotations

import random
from typing import Optional

from . import AbstractAgent
from ..game_model import GameModel, Move, Player, get_legal_move_coords


__author__ = "William Bain"
__copyright__ = "William Bain"
__license__ = "mit"


class RandomAgent(AbstractAgent):
    """An agent which picks a random move"""

    def __init__(self, player):
        self._player = player

    @property
    def player(self) -> Player:
        return self._player

    def choose_move(self, game: GameModel, opponent_move: Optional[Move]) -> Move:
        options = get_legal_move_coords(game)
        assert options, 'Player invoked with no legal moves'

        return Move(player=self.player, coords=random.choice(options))
