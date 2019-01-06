"""Support for writing tact server state to a Redis store
"""

from __future__ import annotations

import enum
import json
import uuid
import typing
from typing import Tuple, Optional

from .import_util import try_server_imports

with try_server_imports():
    import aioredis

from ..game_model import GameModel, Player
from .server import SessionState, GameState, GameMeta, AbstractRedisStore


_EXPECTED_SESSION_STATES = ('need-join', 'running')

_EXPECTED_GAME_STATES = (
    'join-pending-player1',
    'join-pending-player2',
    'running',
    'completed',
)


class RedisStore(AbstractRedisStore):
    def __init__(self, url: str, db=-1) -> None:
        self._url = url
        self._db = db
        self._pool: Optional[aioredis.Redis] = None

    async def get_pool(self) -> aioredis.Redis:
        if self._pool is not None:
            return self._pool

        self._pool = await aioredis.create_redis_pool(self._url)
        if self._db >= 0:
            await self._pool.select(self._db)
        return self._pool

    async def put_session(self, conn_id: str, state: SessionState) -> None:
        """Write a new session into Redis"""

        # TODO: expiry
        redis = await self.get_pool()
        await redis.hmset_dict(
            _conn_id_to_redis_key(conn_id),
            {'state': serialize_enum(state, _EXPECTED_SESSION_STATES)},
        )

    async def read_session(self, conn_id: str) -> SessionState:
        """Read the state of a session from Redis"""
        redis = await self.get_pool()
        state: Optional[str] = await redis.hget(
            _conn_id_to_redis_key(conn_id), 'state', encoding='utf-8'
        )

        # TODO: If there are real scenarios where this could happen
        # it would be better to let the caller handle it
        if state is None:
            raise LookupError(f'Failed to find connection {conn_id}')

        return SessionState(state)

    async def delete_session(self, conn_id: str) -> None:
        """Delete a session from Redis"""
        redis = await self.get_pool()
        await redis.delete(_conn_id_to_redis_key(conn_id))

    async def put_game(self, game: GameModel, meta: GameMeta) -> uuid.UUID:
        """Write a new game into Redis, returning the key"""
        redis = await self.get_pool()
        key = uuid.uuid4()

        fields = encode_game_meta(meta)
        fields.update(encode_game_fields(game))

        # TODO: set a game expiry?
        await redis.hmset_dict(key.bytes, fields)

        return key

    async def update_game(
        self,
        key: bytes,
        game: Optional[GameModel] = None,
        meta: Optional[GameMeta] = None,
    ) -> None:
        """Update the state of the game with the given key"""
        redis = await self.get_pool()
        fields = {}
        if game is not None:
            fields.update(encode_game_fields(game))
        if meta is not None:
            fields.update(encode_game_meta(meta))
        await redis.hmset_dict(key, fields)

    async def read_game(self, key: bytes) -> Tuple[GameState, GameModel]:
        """Read the state of the game with the given key"""
        redis = await self.get_pool()
        out = await redis.hmget(
            key,
            'state',
            'gm_squares',
            'gm_target_len',
            'gm_player',
            'gm_board',
            encoding='utf-8',
        )

        if any(v is None for v in out):
            raise LookupError(
                f'Failed to read desired keys for game {uuid.UUID(bytes=key)}'
            )

        state, squares, target_len, player, board = out

        game_state = GameState(state)
        game = decode_game_fields(
            squares=squares, target_len=target_len, player=player, board=board
        )
        return game_state, game

    async def read_game_meta(self, key: bytes) -> GameMeta:
        redis = await self.get_pool()
        out: Tuple[Optional[bytes], ...] = await redis.hmget(
            key, 'state', 'nonce.p1', 'nonce.p2', 'conn_id.p1', 'conn_id.p2'
        )

        if any(v is None for v in out):
            raise LookupError(
                f'Failed to read desired keys for game {uuid.UUID(bytes=key)}'
            )

        state, nonce_p1, nonce_p2, conn_id_p1, conn_id_p2 = typing.cast(
            Tuple[bytes, ...], out
        )
        return decode_game_meta(
            state=state.decode(),
            nonce_p1=nonce_p1,
            nonce_p2=nonce_p2,
            conn_id_p1=conn_id_p1.decode(),
            conn_id_p2=conn_id_p2.decode(),
        )

    async def delete_game(self, key: bytes):
        """Delete the given game from Redis"""
        redis = await self.get_pool()
        await redis.unlink(key)


#
# SESSION UTILITIES
#


def _conn_id_to_redis_key(conn_id: str) -> str:
    return f'conn:{conn_id}'


#
# GAME UTILITIES
#


def encode_game_fields(game: GameModel) -> dict:
    return {
        'gm_squares': str(game.squares),
        'gm_target_len': str(game.target_len),
        'gm_player': str(game.player),
        'gm_board': json.dumps(game.board),
    }


def decode_game_fields(
    *, squares: str, target_len: str, player: str, board: str
) -> GameModel:
    return GameModel(
        squares=int(squares),
        target_len=int(target_len),
        player=Player(int(player)),
        board=json.loads(board),
    )


def encode_game_meta(meta: GameMeta) -> dict:
    if any(c == '' for c in meta.conn_ids):
        raise ValueError('empty string is not a legal conn_id')

    return {
        'state': serialize_enum(meta.state, _EXPECTED_GAME_STATES),
        'nonce.p1': meta.player_nonces[0].bytes,
        'nonce.p2': meta.player_nonces[1].bytes,
        'conn_id.p1': meta.conn_ids[0] or '',
        'conn_id.p2': meta.conn_ids[1] or '',
    }


def decode_game_meta(
    *, state: str, nonce_p1: bytes, nonce_p2: bytes, conn_id_p1: str, conn_id_p2: str
) -> GameMeta:
    return GameMeta(
        state=GameState(state),
        player_nonces=(uuid.UUID(bytes=nonce_p1), uuid.UUID(bytes=nonce_p2)),
        conn_ids=(conn_id_p1 or None, conn_id_p2 or None),
    )


#
# BASE UTILITIES
#


def serialize_enum(obj: enum.Enum, expected_values: Tuple[str, ...]) -> str:
    if obj.value not in expected_values:
        raise RuntimeError(f'unexpected enum value on serialization: {obj}')
    return obj.value
