"""Support for agents which handle the gameplay of a given player"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

from ..game_model import GameModel, Move


__author__ = "William Bain"
__copyright__ = "William Bain"
__license__ = "mit"


class BaseAgent (ABC):
    """Base class to support agents.

    Agents must implement methods to declare what player they represent and
    to choose moves.
    """
    @property
    @abstractmethod
    def player(self):
        raise NotImplementedError('player')

    def choose_move(self,
                    game: GameModel,
                    opponent_move: Optional[Move]) -> Move:
        """Make a new move.

        The caller is supplied with the current state of the game as well as
        the opponent's last move.
        """
        raise NotImplementedError('choose_move')
