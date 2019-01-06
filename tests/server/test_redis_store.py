# pylint: disable=redefined-outer-name

import uuid
import asyncio

import pytest

from tact.game_model import GameModel, Move
from tact.server.server import SessionState, GameState, GameMeta
from tact.server.redis_store import RedisStore


URL = 'redis://localhost'
TEST_DB_NUMBER = 1

GAME_ID = 'ca112072-ddf0-4839-9db7-f28ca9309ec6'


@pytest.fixture(scope='module')
def redis_test_db_init():
    async def clear_test_db():
        redis_store = RedisStore(URL, db=TEST_DB_NUMBER)
        pool = await redis_store.get_pool()
        await clear_store(pool)

    asyncio.run(clear_test_db())


@pytest.fixture
async def store(redis_test_db_init):  # pylint: disable=unused-argument
    redis_store = RedisStore(URL, db=TEST_DB_NUMBER)
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
    assert (await store.read_session('foo')) == (SessionState.NEED_JOIN, None)

    game_id_bytes = uuid.UUID(GAME_ID).bytes
    await store.put_session('foo', SessionState.RUNNING, game_id_bytes)
    assert (await store.read_session('foo')) == (SessionState.RUNNING, game_id_bytes)

    await store.delete_session('foo')
    await assert_cleared(await store.get_pool())


@pytest.mark.asyncio
async def test_game(store):
    model = GameModel(squares=8, target_len=5)
    meta = GameMeta(
        state=GameState.JOIN_PENDING,
        player_nonces=(uuid.uuid4(), uuid.uuid4()),
        conn_ids=('foo', 'bar'),
    )
    game_id = await store.put_game(model, meta)

    model2 = model.copy()
    model2.apply_move(Move(player=1, coords=(0, 0)))
    meta2 = GameMeta(
        state=GameState.RUNNING,
        player_nonces=meta.player_nonces,
        conn_ids=('foo', None),
    )

    await store.update_game(game_id.bytes, game=model2)
    await store.update_game(game_id.bytes, meta=meta2)

    state_out, model_out = await store.read_game(game_id.bytes)

    assert state_out == GameState.RUNNING
    assert model_out == model2

    meta_out = await store.read_game_meta(game_id.bytes)

    assert meta_out.state == meta2.state
    assert meta_out.player_nonces == meta2.player_nonces
    assert meta_out.conn_ids == meta2.conn_ids

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
