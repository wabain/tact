# pylint: disable=redefined-outer-name

import uuid

import pytest

from tact.game_model import GameModel, Move
from tact.server.server import SessionState, GameState, GameMeta
from tact.server.redis_store import RedisStore


URL = 'redis://localhost'


@pytest.fixture
async def store():
    redis_store = RedisStore('redis://localhost')
    yield redis_store

    pool = await redis_store.get_pool()
    await clear_store(pool)
    pool.close()
    await pool.wait_closed()


@pytest.mark.asyncio
async def test_session(store):
    with pytest.raises(LookupError):
        await store.read_session('foo')

    await store.put_session('foo', SessionState.NEED_JOIN)
    assert (await store.read_session('foo')) == SessionState.NEED_JOIN

    await store.put_session('foo', SessionState.RUNNING)
    assert (await store.read_session('foo')) == SessionState.RUNNING

    await store.delete_session('foo')
    await assert_cleared(await store.get_pool())


@pytest.mark.asyncio
async def test_game(store):
    model = GameModel(squares=8, target_len=5)
    meta = GameMeta(
        state=GameState.JOIN_PENDING_P2, player_nonces=(uuid.uuid4(), uuid.uuid4())
    )
    game_id = await store.put_game(model, meta)

    model2 = model.copy()
    model2.apply_move(Move(player=1, coords=(0, 0)))
    meta2 = GameMeta(state=GameState.RUNNING, player_nonces=meta.player_nonces)

    await store.update_game(game_id.bytes, game=model2)
    await store.update_game(game_id.bytes, meta=meta2)

    state_out, model_out = await store.read_game(game_id.bytes)

    assert state_out == GameState.RUNNING
    assert model_out == model2

    await store.delete_game(game_id.bytes)

    with pytest.raises(LookupError):
        await store.read_game(game_id.bytes)

    await assert_cleared(await store.get_pool())


async def assert_cleared(pool):
    assert await clear_store(pool) == 0


async def clear_store(pool) -> int:
    cur = b'0'
    count = 0
    while cur:
        cur, keys = await pool.scan(cur, match='*')
        count += len(keys)
        if keys:
            await pool.unlink(*keys)
    return count
