from __future__ import annotations

import uuid
import json
from typing import Optional, Tuple
from unittest.mock import Mock, MagicMock

import pytest

from tact.game_model import GameModel, Player

from tact.server import server
from tact.server.server import (
    ServerCtx,
    AbstractRedisStore,
    GameMeta,
    GameState,
    SessionState,
)
from tact.server.websocket import AbstractWSManager, WebsocketConnectionLost


# Mock constants
MOCK_GAME_ID = 'ca112072-ddf0-4839-9db7-f28ca9309ec6'


@pytest.mark.asyncio
async def test_new_connection():
    ctx = mock_server_ctx()
    await server.new_connection(ctx, conn_id='foo')
    ctx.redis_store.mock.put_session.assert_called_with('foo', SessionState.NEED_JOIN)


@pytest.mark.asyncio
async def test_client_message_non_json():
    ctx = mock_server_ctx()
    await server.new_message(ctx, 'foo', 'not valid json!!!')

    ctx.ws_manager.mock.send.assert_called_with(
        'foo',
        {
            'version': '0.1',
            'msg_id': 0,
            'type': 'illegal_msg',
            'msg': {'err_msg_id': None, 'error': 'failed to parse message'},
        },
    )

    # TODO
    with pytest.raises(AssertionError):
        assert_session_cleaned_up(ctx, 'foo')


@pytest.mark.asyncio
async def test_client_message_invalid_type():
    ctx = mock_server_ctx()
    msg = json.dumps({'version': '0.1', 'msg_id': 200, 'type': 'somersault', 'msg': {}})
    await server.new_message(ctx, 'foo', msg)

    ctx.ws_manager.mock.send.assert_called_with(
        'foo',
        {
            'version': '0.1',
            'msg_id': 0,
            'type': 'illegal_msg',
            'msg': {'err_msg_id': 200, 'error': 'invalid input at message.type'},
        },
    )

    # TODO
    with pytest.raises(AssertionError):
        assert_session_cleaned_up(ctx, 'foo')


@pytest.mark.asyncio
async def test_client_message_invalid_msg_id():
    ctx = mock_server_ctx()

    # Message type doesn't matter much here; voluptous will bail before doing
    # that validation
    msg = json.dumps(
        {'version': '0.1', 'msg_id': 'cats', 'type': 'somersault', 'msg': {}}
    )
    await server.new_message(ctx, 'foo', msg)

    ctx.ws_manager.mock.send.assert_called_with(
        'foo',
        {
            'version': '0.1',
            'msg_id': 0,
            'type': 'illegal_msg',
            'msg': {'err_msg_id': None, 'error': 'invalid input at message.msg_id'},
        },
    )

    # TODO
    with pytest.raises(AssertionError):
        assert_session_cleaned_up(ctx, 'foo')


@pytest.mark.asyncio
async def test_client_message_reply_illegal_msg():
    ctx = mock_server_ctx()

    # Message type doesn't matter much here; voluptous will bail before doing
    # the granular validation
    msg = json.dumps(
        {
            'version': '0.1',
            'msg_id': 10,
            'type': 'illegal_msg',
            'msg': {'err_msg_id': None, 'error': "I don't like it"},
        }
    )
    await server.new_message(ctx, 'foo', msg)
    assert_session_cleaned_up(ctx, 'foo')


@pytest.mark.asyncio
@pytest.mark.parametrize('player', [1, 2])
async def test_client_message_new_game(player: Player):
    ctx = mock_server_ctx()

    put_game = Mock(return_value=uuid.UUID(MOCK_GAME_ID))
    ctx.redis_store.mock.put_game = put_game

    # Message type doesn't matter much here; voluptous will bail before doing
    # the granular validation
    msg = json.dumps(
        {
            'version': '0.1',
            'msg_id': 10,
            'type': 'new_game',
            'msg': {'player': player, 'squares_per_row': 8, 'run_to_win': 5},
        }
    )

    await server.new_message(ctx, 'foo', msg)

    ctx.redis_store.mock.put_session.assert_called_with('foo', SessionState.RUNNING)

    assert len(put_game.mock_calls) == 1
    _, (game_model, game_meta), _ = put_game.mock_calls[0]
    assert game_model == GameModel(squares=8, target_len=5)

    if player == 1:
        expected_game_state = GameState.JOIN_PENDING_P2
    else:
        expected_game_state = GameState.JOIN_PENDING_P1

    assert game_meta.state == expected_game_state
    player_nonce = game_meta.get_player_nonce(player)

    ctx.ws_manager.mock.send.assert_called_with(
        'foo',
        {
            'version': '0.1',
            'msg_id': 0,
            'type': 'game_joined',
            'msg': {
                'player': player,
                'squares_per_row': 8,
                'run_to_win': 5,
                'game_id': MOCK_GAME_ID,
                'player_nonce': str(player_nonce),
            },
        },
    )


def assert_session_cleaned_up(ctx: ServerCtx, conn_id: str) -> None:
    ctx.ws_manager.mock.close.assert_called_with(conn_id)
    ctx.redis_store.mock.delete_session.assert_called_with(conn_id)


def mock_server_ctx() -> ServerCtx:
    return ServerCtx(redis_store=MockRedisStore(), ws_manager=MockWSManager())


class MockWSManager(AbstractWSManager):
    def __init__(self):
        self.mock = MagicMock()

    async def send(self, conn_id: str, msg: str) -> None:
        return self.mock.send(conn_id, msg)

    async def close(self, conn_id: str):
        return self.mock.close(conn_id)


class MockRedisStore(AbstractRedisStore):
    def __init__(self):
        self.mock = MagicMock()

        # Force functions with return values to be handled on a case-by-case basis
        self.mock.put_game = MagicMock(side_effect=NotImplementedError)
        self.mock.read_session = MagicMock(side_effect=NotImplementedError)
        self.mock.read_game = MagicMock(side_effect=NotImplementedError)

    async def put_session(self, conn_id: str, state: SessionState) -> None:
        return self.mock.put_session(conn_id, state)

    async def read_session(self, conn_id: str) -> SessionState:
        return self.mock.read_session(conn_id)

    async def delete_session(self, conn_id: str) -> None:
        return self.mock.delete_session(conn_id)

    async def put_game(self, game: GameModel, meta: GameMeta) -> uuid.UUID:
        return self.mock.put_game(game, meta)

    async def update_game(
        self,
        key: bytes,
        game: Optional[GameModel] = None,
        meta: Optional[GameMeta] = None,
    ) -> None:
        return self.mock.update_game(key, game, meta)

    async def read_game(self, key: bytes) -> Tuple[GameState, GameModel]:
        return self.mock.read_game(key)

    async def delete_game(self, key: bytes):
        return self.mock.delete_game(key)
