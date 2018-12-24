from __future__ import annotations

import random
from typing import Optional

from . import AbstractAgent
from ..game_model import GameModel, Move, Player, get_legal_move_coords


__author__ = "Alun Bain"
__copyright__ = "Alun Bain"
__license__ = "mit"


class AlunAgent (AbstractAgent):
    def __init__(self, player):
        self._player = player

    @property
    def player(self) -> Player:
        return self._player

    def choose_move(self,
                    game: GameModel,
                    opponent_move: Optional[Move]) -> Move:
        options = get_legal_move_coords(game)
        assert options, 'Player invoked with no legal moves'
        return choose_legal_move(self.player, game, options, opponent_move)


def choose_legal_move(player, game, legal_coords, opponent_move):
    """
    Pick a legal move and return a Move object.

    player: The player the agent is playing for (possible values: 1 or 2)

    game: The current game state. Relevant properties:

        game.squares: The number of squares along each dimension of the game
            board.

        game.target_len: The number of pieces in a row needed to win.

        game.board: The game board as a two-dimensional list where each square
            (x, y) can be accessed with game.board[x][y]. Possible values for
            a square are None, or 1 or 1 if a player has entered that square.

    legal_coords: A list of tuples (x, y) which can legally be moved to.

    opponent_move: The last move made by the opponent (or None if this is the
        first move).
    """
    # Pick the first-listed legal coordinates
    # TODO: implement a competitive strategy
    coords = legal_coords[0]

    return Move(player=player, coords=coords)
