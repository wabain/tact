"""Core gameplay constructs"""

from __future__ import annotations

import sys
from enum import Enum
from typing import Iterator, NewType, List, Tuple, Optional

__author__ = "William Bain"
__copyright__ = "William Bain"
__license__ = "mit"

Player = NewType('Player', int)
Board = List[List[Optional[Player]]]


class GameStatus (Enum):
    Drawn = -1
    Ongoing = 0
    PlayerOneWins = 1
    PlayerTwoWins = 2


class Move:  # pylint: disable=too-few-public-methods
    def __init__(self, player: Player, coords: Tuple[int, int]) -> None:
        self.player = player
        self.coords = coords

    def __repr__(self):
        return f'{type(self).__name__}(player={self.player}, coords={self.coords})'


class IllegalMoveException (Exception):
    def __init__(self, move: Move, msg: str) -> None:
        super().__init__(msg)
        self.move = move

    def __str__(self):
        return f'{self.move!r}: {super().__str__()}'


class GameModel:
    def __init__(self,
                 *,
                 squares: int,
                 target_len: int,
                 player: Optional[Player] = None,
                 board: Optional[Board] = None) -> None:
        self.squares = squares
        self.target_len = target_len
        self.player = player or Player(1)
        self.board = board or [[None] * squares for _ in range(squares)]

        if not 0 < target_len <= squares:
            raise ValueError('values for squares or target_len invalid')

        if board and (len(board) != squares or any(len(r) != squares for r in board)):
            raise ValueError('incorrect board dimensions')

    def copy(self) -> GameModel:
        return GameModel(squares=self.squares,
                         target_len=self.target_len,
                         player=self.player,
                         board=[list(r) for r in self.board])

    def apply_move(self, move: Move):
        status = self.status()
        if status != GameStatus.Ongoing:
            raise IllegalMoveException(move, f'Game is in state {status.name}')

        if move.player != self.player:
            raise IllegalMoveException(move, f'Expected player {self.player}')

        x, y = move.coords

        if not all(0 <= c < self.squares for c in move.coords):
            raise IllegalMoveException(move, 'Coordinates out of bounds')

        if self.board[x][y] is not None:
            raise IllegalMoveException(move, 'Square is already occupied')

        self.board[x][y] = move.player
        self.player = get_opponent(move.player)

    def status(self) -> GameStatus:
        has_potential = False

        for run in self._runs():
            winner = self._run_winner(run)
            if winner is not None:
                return winner

            has_potential = has_potential or self._is_potential_run(run)

        if not has_potential:
            return GameStatus.Drawn

        return GameStatus.Ongoing

    def _run_winner(self, run: Tuple[Optional[Player], ...]) -> Optional[GameStatus]:
        assert len(run) >= self.target_len

        for i in range(len(run) - self.target_len + 1):
            start = run[i]
            if start is None:
                continue
            if all(run[i + j] == start for j in range(1, self.target_len)):
                return GameStatus(start)

        return None

    def _is_potential_run(self, run: Tuple[Optional[Player], ...]) -> bool:
        assert len(run) >= self.target_len

        for player in (1, 2):
            for i in range(len(run) - self.target_len + 1):
                if all(run[i + j] in (None, player) for j in range(self.target_len)):
                    return True

        return False


    def _runs(self) -> Iterator[Tuple[Optional[Player], ...]]:
        for run_idx in self._run_idxs():
            yield tuple(self.board[x][y] for x, y in run_idx)

    def _run_idxs(self) -> Iterator[Tuple[Tuple[int, int], ...]]:
        for i in range(self.squares):
            yield tuple((i, j) for j in range(self.squares))

        for i in range(self.squares):
            yield tuple((j, i) for j in range(self.squares))

        for forward in (True, False):
            for offset in range(-self.squares, self.squares):
                run = []

                for i in range(self.squares):
                    if not (0 <= i + offset < self.squares):
                        continue

                    run.append((i + offset, i if forward else self.squares - i - 1))

                if len(run) >= self.target_len:
                    yield tuple(run)

    def dump_board(self, out=sys.stdout):
        self._print_sep(out)
        for i in range(len(self.board)):
            print(end='|', file=out)
            for col in self.board:
                square = col[i]
                char = 'X' if square == 1 else 'O' if square == 2 else ' '
                print(f' {char} |', end='', file=out)
            print(file=out)
            self._print_sep(out)

    def _print_sep(self, out):
        print('-' * (self.squares * 4 + 1), file=out)

    def __eq__(self, other):
        if not isinstance(other, GameModel):
            return False

        return (
            self.squares == other.squares and
            self.target_len == other.target_len and
            self.player == other.player and
            self.board == other.board
        )


#
# Utilities
#

def get_opponent(player: Player) -> Player:
    return Player(2 if player == 1 else 1)


def get_legal_move_coords(game: GameModel) -> List[Tuple[int, int]]:
    coords = []
    for x in range(game.squares):
        for y in range(game.squares):
            if game.board[x][y] is None:
                coords.append((x, y))
    return coords
