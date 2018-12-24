import pytest
import asyncio
from io import StringIO
from tact.game_model import IllegalMoveException, Move, GameStatus
from tact.game_runner import InMemoryGameRunner

__author__ = "William Bain"
__copyright__ = "William Bain"
__license__ = "mit"


@pytest.mark.asyncio
async def test_in_memory_game_runner_claims():
    runner = InMemoryGameRunner(squares=8, target_len=5)

    await runner.claim_player(1)

    with pytest.raises(RuntimeError):
        await runner.claim_player(1)

    with pytest.raises(RuntimeError):
        await runner.launch()

    await runner.claim_player(2)

    with pytest.raises(RuntimeError):
        await runner.send_move(Move(player=1, coords=(0, 0)))

    with pytest.raises(RuntimeError):
        await runner.opposing_move(player=1)

    await runner.launch()

    with pytest.raises(RuntimeError):
        await runner.launch()

@pytest.mark.asyncio
async def test_in_memory_game_runner_sched():
    runner = InMemoryGameRunner(squares=8, target_len=5)

    await runner.claim_player(1)
    await runner.claim_player(2)
    await runner.launch()

    t1 = asyncio.create_task(runner.opposing_move(2))
    done, pending = await asyncio.wait([t1], timeout=0)
    assert pending == {t1}, 'Waits until opposing player moves'
    assert done == set()

    initial_move = Move(player=1, coords=(0, 0))
    status = await runner.send_move(initial_move)
    assert status == GameStatus.Ongoing
    assert runner.game.board[0][0] == 1

    t2 = asyncio.create_task(runner.opposing_move(2))
    done, pending = await asyncio.wait([t1, t2], timeout=0)
    assert done == {t1, t2}, 'Resolves all opposing_move awaits after opponent plays'
    assert pending == set()

    assert t1.result() == (initial_move, runner.game)
    assert t2.result() == (initial_move, runner.game)
