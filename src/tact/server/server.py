"""Core utilities for a gameserver

Because this module is designed to ***, it does not implement top-level
handlers but only the ***.
"""

from __future__ import annotations

import os
import enum
import json
import asyncio
import uuid
import typing
from typing import Tuple

from .import_util import try_server_imports

with try_server_imports():
    from voluptuous import MultipleInvalid

from ..game_model import GameModel, Player

from . import wire
from . import redis_store
from .handlers import HandlerSet, handler


class SessionState(enum.Enum):
    """State of a client session"""

    NEED_JOIN = 'need-join'
    RUNNING = 'running'


class GameState(enum.Enum):
    """State of a server-managed game"""

    JOIN_PENDING_P1 = 'join-pending-player1'
    JOIN_PENDING_P2 = 'join-pending-player2'
    RUNNING = 'running'
    COMPLETED = 'completed'


class GameMeta:
    """Metadata associated with a server-managed game"""

    def __init__(
        self, state: GameState, player_nonces: Tuple[uuid.UUID, uuid.UUID]
    ) -> None:
        self.state = state
        self.player_nonces = player_nonces

    def get_player_nonce(self, player: Player) -> uuid.UUID:
        return self.player_nonces[0 if player == 1 else 1]


async def new_connection(conn_id: str) -> None:
    await redis_store.put_session(conn_id, SessionState.NEED_JOIN)


async def new_message(conn_id: str, msg_src: str, ws_manager) -> None:
    try:
        msg = json.loads(msg_src)
    except ValueError:
        await ws_manager.send(
            conn_id,
            wire.ServerMessage.build(
                wire.ServerMsgType.ILLEGAL_MSG,
                msg_id=0,  # TODO
                err_msg_id=None,
                error='failed to parse message',
            ),
        )

        return

    try:
        msg_type, payload = wire.ClientMessage.parse(msg)
    except MultipleInvalid as exc:
        err_msg_id = msg.get('msg_id') if isinstance(msg, dict) else None
        if err_msg_id is not None and not isinstance(err_msg_id, int):
            err_msg_id = None

        await ws_manager.send(
            conn_id,
            wire.ServerMessage.build(
                wire.ServerMsgType.ILLEGAL_MSG,
                msg_id=0,  # TODO
                err_msg_id=err_msg_id,
                error=str(exc),
            ),
        )

        return

    typing.cast(
        HandlerSet[wire.ClientMsgType], OnClientMessage.dispatch(msg_type, payload)
    )


class WebsocketConnectionLost(Exception):
    pass


if typing.TYPE_CHECKING:

    class BaseOnClientMessage(HandlerSet[wire.ClientMsgType]):
        pass


else:

    class BaseOnClientMessage(HandlerSet):
        pass


class OnClientMessage(BaseOnClientMessage):
    @handler(wire.ClientMsgType.ILLEGAL_MSG)
    @staticmethod
    async def on_illegal_msg(conn_id, payload, ws_manager):
        await asyncio.gather(
            redis_store.delete_session(conn_id), ws_manager.close(conn_id)
        )

    @handler(wire.ClientMsgType.NEW_GAME)
    @staticmethod
    async def on_new_game(conn_id, payload, ws_manager):
        player = payload['player']
        squares = payload['squares_per_row']
        target_len = payload['run_to_win']

        if player == 1:
            state = GameState.JOIN_PENDING_P2
        else:
            assert player == 2
            state = GameState.JOIN_PENDING_P1

        # TODO: handle validation of relative values of params
        game = GameModel(squares=squares, target_len=target_len)

        meta = GameMeta(
            state=state,
            player_nonces=(uuid.uuid4(), uuid.uuid4()),
            # join_conns=(conn_id, None) if player == 1 else (None, conn_id),
        )

        # TODO: validate state transitions?
        game_key, _ = await asyncio.gather(
            redis_store.put_game(game=game, meta=meta),
            redis_store.put_session(conn_id, SessionState.RUNNING),
        )

        try:
            await ws_manager.send(
                conn_id,
                wire.ServerMessage.build(
                    wire.ServerMsgType.GAME_JOINED,
                    msg_id=0,  # TODO
                    game_id=str(game_key),  # TODO
                    player_nonce=meta.get_player_nonce(player),
                ),
            )
        except WebsocketConnectionLost:
            await asyncio.gather(
                redis_store.delete_game(game_key), redis_store.delete_session(conn_id)
            )

    @handler(wire.ClientMsgType.JOIN_GAME)
    @staticmethod
    async def on_join_game(payload):
        pass

    @handler(wire.ClientMsgType.REJOIN_GAME)
    @staticmethod
    async def on_rejoin_game(msg):
        raise NotImplementedError('on rejoin game')

    # @handler(wire.ClientMsgType.NEW_MOVE)
    # async def on_new_move(msg):
    #     pass
