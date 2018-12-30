from io import StringIO
import pytest
from tact.game_model import GameModel, GameStatus, IllegalMoveException, Move


__author__ = "William Bain"
__copyright__ = "William Bain"
__license__ = "mit"


def test_game_model_init():
    with pytest.raises(ValueError):
        GameModel(squares=8, target_len=12)

    with pytest.raises(ValueError):
        GameModel(squares=8, target_len=5, board=[[]])

    GameModel(squares=8, target_len=5)


def test_game_model_apply_move():
    model = GameModel(squares=8, target_len=5)

    model.apply_move(Move(player=1, coords=(0, 0)))

    assert model.player == 2
    assert model.board[0][0] == 1

    with pytest.raises(IllegalMoveException, match='^Move(.*?): Expected player 2$'):
        model.apply_move(Move(player=1, coords=(0, 1)))

    with pytest.raises(
        IllegalMoveException, match='^Move(.*?): Coordinates out of bounds$'
    ):
        model.apply_move(Move(player=2, coords=(-1, 0)))

    with pytest.raises(
        IllegalMoveException, match='^Move(.*?): Square is already occupied$'
    ):
        model.apply_move(Move(player=2, coords=(0, 0)))


def test_game_model_to_draw():
    model = GameModel(squares=3, target_len=3)

    model.apply_move(Move(player=1, coords=(0, 0)))
    model.apply_move(Move(player=2, coords=(1, 1)))

    model.apply_move(Move(player=1, coords=(2, 0)))
    model.apply_move(Move(player=2, coords=(1, 0)))

    model.apply_move(Move(player=1, coords=(1, 2)))
    model.apply_move(Move(player=2, coords=(2, 1)))

    model.apply_move(Move(player=1, coords=(0, 1)))
    model.apply_move(Move(player=2, coords=(0, 2)))

    assert model.status() == GameStatus.Drawn

    with pytest.raises(
        IllegalMoveException, match=f'^Move(.*?): Game is in state Drawn$'
    ):
        model.apply_move(Move(player=1, coords=(2, 2)))

    with StringIO() as out:
        model.dump_board(out=out)
        dumped = out.getvalue()

    assert dumped == (
        '-------------\n'
        '| X | O | X |\n'
        '-------------\n'
        '| X | O | O |\n'
        '-------------\n'
        '| O | X |   |\n'
        '-------------\n'
    )


def test_game_model_to_victory():
    model = GameModel(squares=5, target_len=3)

    model.apply_move(Move(player=1, coords=(2, 2)))
    model.apply_move(Move(player=2, coords=(1, 2)))

    model.apply_move(Move(player=1, coords=(1, 3)))
    model.apply_move(Move(player=2, coords=(0, 3)))

    model.apply_move(Move(player=1, coords=(2, 1)))
    model.apply_move(Move(player=2, coords=(2, 3)))

    model.apply_move(Move(player=1, coords=(2, 0)))

    assert model.status() == GameStatus.PlayerOneWins

    with pytest.raises(
        IllegalMoveException, match=f'^Move(.*?): Game is in state PlayerOneWins$'
    ):
        model.apply_move(Move(player=2, coords=(0, 1)))

    with StringIO() as out:
        model.dump_board(out=out)
        dumped = out.getvalue()

    assert dumped == (
        '---------------------\n'
        '|   |   | X |   |   |\n'
        '---------------------\n'
        '|   |   | X |   |   |\n'
        '---------------------\n'
        '|   | O | X |   |   |\n'
        '---------------------\n'
        '| O | X | O |   |   |\n'
        '---------------------\n'
        '|   |   |   |   |   |\n'
        '---------------------\n'
    )
