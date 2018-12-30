"""Core utilities for a gameserver

Because this module is designed to ***, it does not implement top-level
handlers but only the ***.
"""

from __future__ import annotations

import enum
import json
import asyncio
import uuid
import typing
from typing import Any, List, Tuple, Optional
from abc import ABC, abstractmethod

from voluptuous import MultipleInvalid

from ..game_model import GameModel, Player
from ..networking import wire
from ..networking.handlers import HandlerSet, handler
from .websocket import AbstractWSManager, WebsocketConnectionLost


#
# SERVER TYPES
#


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


class GameMeta:  # pylint: disable=too-few-public-methods
    """Metadata associated with a server-managed game"""

    def __init__(
        self, state: GameState, player_nonces: Tuple[uuid.UUID, uuid.UUID]
    ) -> None:
        self.state = state
        self.player_nonces = player_nonces

    def get_player_nonce(self, player: Player) -> uuid.UUID:
        return self.player_nonces[0 if player == 1 else 1]


class ServerCtx:  # pylint: disable=too-few-public-methods
    """A context object exposing services for server callbacks"""

    def __init__(self, redis_store: AbstractRedisStore, ws_manager: AbstractWSManager):
        self.redis_store = redis_store
        self.ws_manager = ws_manager


#
# SERVER HANDLER FUNCTIONS
#


async def new_connection(ctx: ServerCtx, conn_id: str) -> None:
    await ctx.redis_store.put_session(conn_id, SessionState.NEED_JOIN)


async def new_message(ctx: ServerCtx, conn_id: str, msg_src: str) -> None:
    try:
        msg = json.loads(msg_src)
    except ValueError:
        await ctx.ws_manager.send(
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

        await ctx.ws_manager.send(
            conn_id,
            wire.ServerMessage.build(
                wire.ServerMsgType.ILLEGAL_MSG,
                msg_id=0,  # TODO
                err_msg_id=err_msg_id,
                error=format_validation_error(exc),
            ),
        )

        return

    await OnClientMessage.dispatch(msg_type, ctx=ctx, conn_id=conn_id, payload=payload)


def format_validation_error(exc: MultipleInvalid) -> str:
    paths = [error.path for error in exc.errors]

    # Hack: if the message type is invalid, voluptuous may spill out
    # additional errors from the msg payload that it gathered while
    # trying to validate the type/payload combination; filter those out.
    if ['type'] in paths:
        paths = [p for p in paths if not p or p[0] != 'msg']

    formatted = [format_validation_error_path(path) for path in paths]
    return 'invalid input at ' + ', '.join(formatted)


def format_validation_error_path(path: List[Any]):
    return 'message' + ''.join(
        '.' + p if isinstance(p, str) else f'[{p!r}]' for p in path
    )


#
# MESSAGE HANDLER FUNCTIONS
#

if typing.TYPE_CHECKING:  # pragma: no cover
    # pylint: disable=too-few-public-methods
    class BaseOnClientMessage(HandlerSet[wire.ClientMsgType]):
        pass


else:

    class BaseOnClientMessage(HandlerSet):  # pylint: disable=too-few-public-methods
        pass


class OnClientMessage(BaseOnClientMessage):
    # Handler callbacks must all have the same arguments
    #
    # pylint: disable=unused-argument

    @handler(wire.ClientMsgType.ILLEGAL_MSG)
    @staticmethod
    async def on_illegal_msg(*, ctx: ServerCtx, conn_id: str, payload: dict):
        await asyncio.gather(
            ctx.redis_store.delete_session(conn_id), ctx.ws_manager.close(conn_id)
        )

    @handler(wire.ClientMsgType.NEW_GAME)
    @staticmethod
    async def on_new_game(*, ctx: ServerCtx, conn_id: str, payload: dict):
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
            ctx.redis_store.put_game(game=game, meta=meta),
            ctx.redis_store.put_session(conn_id, SessionState.RUNNING),
        )

        try:
            await ctx.ws_manager.send(
                conn_id,
                wire.ServerMessage.build(
                    wire.ServerMsgType.GAME_JOINED,
                    msg_id=0,  # TODO
                    game_id=str(game_key),  # TODO
                    player_nonce=str(meta.get_player_nonce(player)),
                ),
            )
        except WebsocketConnectionLost:
            await asyncio.gather(
                ctx.redis_store.delete_game(game_key.bytes),
                ctx.redis_store.delete_session(conn_id),
            )

    @handler(wire.ClientMsgType.JOIN_GAME)
    @staticmethod
    async def on_join_game(*, ctx: ServerCtx, conn_id: str, payload: dict):
        pass

    @handler(wire.ClientMsgType.REJOIN_GAME)
    @staticmethod
    async def on_rejoin_game(*, ctx: ServerCtx, conn_id: str, payload: dict):
        raise NotImplementedError('on rejoin game')

    # @handler(wire.ClientMsgType.NEW_MOVE)
    # async def on_new_move(*, ctx: ServerCtx, conn_id: str, payload: dict):
    #     pass


#
# REDIS INTERFACE
#


class AbstractRedisStore(ABC):
    @abstractmethod
    async def put_session(self, conn_id: str, state: SessionState) -> None:
        """Write a new session into Redis"""
        raise NotImplementedError

    @abstractmethod
    async def read_session(self, conn_id: str) -> SessionState:
        """Read the state of a session from Redis"""
        raise NotImplementedError

    @abstractmethod
    async def delete_session(self, conn_id: str) -> None:
        """Delete a session from Redis"""
        raise NotImplementedError

    @abstractmethod
    async def put_game(self, game: GameModel, meta: GameMeta) -> uuid.UUID:
        """Write a new game into Redis, returning the key"""
        raise NotImplementedError

    @abstractmethod
    async def update_game(
        self,
        key: bytes,
        game: Optional[GameModel] = None,
        meta: Optional[GameMeta] = None,
    ) -> None:
        """Update the state of the game with the given key"""
        raise NotImplementedError

    @abstractmethod
    async def read_game(self, key: bytes) -> Tuple[GameState, GameModel]:
        """Read the state of the game with the given key"""
        raise NotImplementedError

    @abstractmethod
    async def delete_game(self, key: bytes):
        """Delete the given game from Redis"""
        raise NotImplementedError
