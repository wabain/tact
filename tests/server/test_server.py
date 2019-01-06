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
    ctx.redis_store.mock.put_session.assert_called_with(
        'foo', SessionState.NEED_JOIN, None
    )


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

    # Message payload doesn't matter much here; voluptous will bail before doing
    # that validation
    msg = json.dumps(
        {'version': '0.1', 'msg_id': 'cats', 'type': 'new_game', 'msg': {}}
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
@pytest.mark.parametrize(
    'player', [pytest.param(1, id='join_player1'), pytest.param(2, id='join_player2')]
)
@pytest.mark.parametrize(
    'conn_lost',
    [pytest.param(False, id='conn_stable'), pytest.param(True, id='conn_lost')],
)
async def test_client_message_new_game(player: Player, conn_lost: bool):
    """Test handling of new_game messages

    Parameters:
    player: player one or two joined the game
    conn_lost: whether the reply send to the player succeeded succeeded
    """
    mock_game_uuid = uuid.UUID(MOCK_GAME_ID)
    ctx = mock_server_ctx()

    if conn_lost:
        ctx.ws_manager.mock.send = Mock(side_effect=WebsocketConnectionLost)

    ctx.redis_store.mock.read_session = Mock(
        return_value=(SessionState.NEED_JOIN, None)
    )

    put_game = Mock(return_value=mock_game_uuid)
    ctx.redis_store.mock.put_game = put_game

    msg = json.dumps(
        {
            'version': '0.1',
            'msg_id': 10,
            'type': 'new_game',
            'msg': {'player': player, 'squares_per_row': 8, 'run_to_win': 5},
        }
    )

    await server.new_message(ctx, 'foo', msg)

    ctx.redis_store.mock.put_session.assert_called_with(
        'foo', SessionState.NEED_JOIN_ACK, mock_game_uuid.bytes
    )

    assert len(put_game.mock_calls) == 1
    _, (game_model, game_meta), _ = put_game.mock_calls[0]
    assert game_model == GameModel(squares=8, target_len=5)

    assert game_meta.state == GameState.JOIN_PENDING
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

    if conn_lost:
        ctx.redis_store.mock.delete_game.assert_called_with(mock_game_uuid.bytes)
        ctx.redis_store.mock.delete_session.assert_called_with('foo')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'player', [pytest.param(1, id='join_player1'), pytest.param(2, id='join_player2')]
)
@pytest.mark.parametrize(
    'conn_lost',
    [pytest.param(False, id='conn_stable'), pytest.param(True, id='conn_lost')],
)
async def test_client_message_join_game(player: Player, conn_lost: bool):
    """Test handling of join_game messages

    Parameters:
    player: player one or two joined the game
    conn_lost: whether the reply send to the player succeeded succeeded
    """
    mock_game_uuid = uuid.UUID(MOCK_GAME_ID)

    game_model = GameModel(squares=8, target_len=5)

    game_meta = GameMeta(
        state=GameState.JOIN_PENDING,
        player_nonces=(uuid.uuid4(), uuid.uuid4()),
        conn_ids=(None, 'bar') if player == 1 else ('bar', None),
    )

    # Configure mocks
    ctx = mock_server_ctx()
    ctx.redis_store.mock.read_session = Mock(
        return_value=(SessionState.NEED_JOIN, None)
    )
    ctx.redis_store.mock.read_game = Mock(return_value=(game_meta.state, game_model))
    ctx.redis_store.mock.read_game_meta = Mock(return_value=game_meta)

    if conn_lost:
        ctx.ws_manager.mock.send = Mock(side_effect=WebsocketConnectionLost)

    # Dispatch message
    msg = json.dumps(
        {
            'version': '0.1',
            'msg_id': 10,
            'type': 'join_game',
            'msg': {'game_id': MOCK_GAME_ID, 'player': player},
        }
    )

    await server.new_message(ctx, 'foo', msg)

    ctx.redis_store.mock.put_session.assert_called_with(
        'foo', SessionState.NEED_JOIN_ACK, mock_game_uuid.bytes
    )

    update_game_mock = ctx.redis_store.mock.update_game
    assert len(update_game_mock.mock_calls) == 2 if conn_lost else 1
    _, (game_key_out, _game_out, meta_out), _ = update_game_mock.mock_calls[0]
    assert game_key_out == mock_game_uuid.bytes
    assert meta_out.state == GameState.JOIN_PENDING
    assert meta_out.player_nonces == game_meta.player_nonces

    if player == 1:
        assert meta_out.conn_ids == ('foo', 'bar')
    else:
        assert meta_out.conn_ids == ('bar', 'foo')

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
                'player_nonce': str(game_meta.get_player_nonce(player)),
            },
        },
    )

    if conn_lost:
        ctx.redis_store.mock.delete_session.assert_called_with('foo')

        _, (game_key_out, _game_out, meta_out), _ = update_game_mock.mock_calls[1]
        assert game_key_out == mock_game_uuid.bytes
        assert meta_out.state == GameState.JOIN_PENDING

        if player == 1:
            assert meta_out.conn_ids == (None, 'bar')
        else:
            assert meta_out.conn_ids == ('bar', None)


def assert_session_cleaned_up(ctx: ServerCtx, conn_id: str) -> None:
    ctx.ws_manager.mock.close.assert_called_with(conn_id)
    ctx.redis_store.mock.delete_session.assert_called_with(conn_id)


def mock_server_ctx() -> ServerCtx:
    return ServerCtx(redis_store=MockRedisStore(), ws_manager=MockWSManager())


class MockWSManager(AbstractWSManager):
    def __init__(self):
        self.mock = MagicMock()

    async def send(self, conn_id: str, msg: dict) -> None:
        return self.mock.send(conn_id, msg)

    async def _send_serialized(self, conn_id: str, msg: str) -> None:
        # pylint: disable=protected-access
        return self.mock._send_serialized(conn_id, msg)

    async def close(self, conn_id: str):
        return self.mock.close(conn_id)


class MockRedisStore(AbstractRedisStore):
    def __init__(self):
        self.mock = MagicMock()

        # Force functions with return values to be handled on a case-by-case basis
        self.mock.put_game = MagicMock(side_effect=NotImplementedError)
        self.mock.read_session = MagicMock(side_effect=NotImplementedError)
        self.mock.read_game = MagicMock(side_effect=NotImplementedError)
        self.mock.read_game_meta = MagicMock(side_effect=NotImplementedError)

    async def put_session(
        self, conn_id: str, state: SessionState, game_id: Optional[bytes] = None
    ) -> None:
        return self.mock.put_session(conn_id, state, game_id)

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

    async def read_game_meta(self, key: bytes) -> GameMeta:
        return self.mock.read_game_meta(key)

    async def delete_game(self, key: bytes):
        return self.mock.delete_game(key)
