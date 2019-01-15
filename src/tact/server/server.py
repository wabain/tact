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
from structlog import get_logger, BoundLoggerBase as Logger

from ..game_model import GameModel, Player, get_opponent
from ..networking import wire
from ..networking.handlers import HandlerSet, handler
from .websocket import AbstractWSManager, WebsocketConnectionLost


logger = get_logger()  # pylint: disable=invalid-name


#
# SERVER TYPES
#


class SessionState(enum.Enum):
    """State of a client session"""

    NEED_JOIN = 'need-join'
    NEED_JOIN_ACK = 'need-join-ack'
    RUNNING = 'running'


class GameState(enum.Enum):
    """State of a server-managed game"""

    JOIN_PENDING = 'join-pending'
    RUNNING = 'running'
    COMPLETED = 'completed'


class GameMeta:  # pylint: disable=too-few-public-methods
    """Metadata associated with a server-managed game"""

    def __init__(
        self,
        state: GameState,
        player_nonces: Tuple[uuid.UUID, uuid.UUID],
        conn_ids: Tuple[Optional[str], Optional[str]],
    ) -> None:
        self.state = state
        self.player_nonces = player_nonces
        self.conn_ids = conn_ids

    def with_state(self, state: GameState) -> GameMeta:
        return GameMeta(
            state=state, player_nonces=self.player_nonces, conn_ids=self.conn_ids
        )

    def get_player_nonce(self, player: Player) -> uuid.UUID:
        return self.player_nonces[0 if player == 1 else 1]

    def get_conn_id(self, player: Player) -> Optional[str]:
        return self.conn_ids[0 if player == 1 else 1]

    def with_conn_id(self, player: Player, conn_id: Optional[str]) -> GameMeta:
        cid1, cid2 = self.conn_ids
        if player == 1:
            cid1 = conn_id
        else:
            cid2 = conn_id
        return GameMeta(
            state=self.state, player_nonces=self.player_nonces, conn_ids=(cid1, cid2)
        )


class ServerCtx:  # pylint: disable=too-few-public-methods
    """A context object exposing services for server callbacks"""

    def __init__(self, redis_store: AbstractRedisStore, ws_manager: AbstractWSManager):
        self.redis_store = redis_store
        self.ws_manager = ws_manager


#
# SERVER HANDLER FUNCTIONS
#


async def new_connection(ctx: ServerCtx, conn_id: str) -> None:
    logger.msg('new connection', conn_id=conn_id)
    await ctx.redis_store.put_session(conn_id, SessionState.NEED_JOIN)


async def new_message(ctx: ServerCtx, conn_id: str, msg_src: str) -> None:
    log = logger.bind(conn_id=conn_id)

    try:
        msg = json.loads(msg_src)
    except ValueError:
        log.msg('failed to parse message JSON')

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
        msg_type, msg_id, payload = wire.ClientMessage.parse(msg)
    except MultipleInvalid as exc:
        err_msg_id = msg.get('msg_id') if isinstance(msg, dict) else None
        if err_msg_id is not None and not isinstance(err_msg_id, int):
            err_msg_id = None

        log.msg('failed to deserialize message', msg_id=err_msg_id)

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

    log = log.bind(msg_id=msg_id, msg_type=msg_type.value)

    log.msg('new message')

    # Filling in the generic type via inheritance in OnClientMessage doesn't
    # seem to be working - https://github.com/python/mypy/issues/1337 ?
    #
    # This cast makes the code typecheck with mypy 0.650, but it doesn't seem
    # to actually validate the msg_type argument.
    dispatch = typing.cast(
        'HandlerSet[wire.ClientMsgType].dispatch', OnClientMessage.dispatch
    )
    await dispatch(
        msg_type, log=log, ctx=ctx, conn_id=conn_id, msg_id=msg_id, payload=payload
    )


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


class OnClientMessage(HandlerSet[wire.ClientMsgType]):
    # Handler callbacks must all have the same arguments
    #
    # pylint: disable=unused-argument

    @handler(wire.ClientMsgType.ILLEGAL_MSG)
    @staticmethod
    async def on_illegal_msg(
        *, log: Logger, ctx: ServerCtx, conn_id: str, msg_id: int, payload: dict
    ):
        await asyncio.gather(
            ctx.redis_store.delete_session(conn_id), ctx.ws_manager.close(conn_id)
        )

    @handler(wire.ClientMsgType.NEW_GAME)
    @staticmethod
    async def on_new_game(
        *, log: Logger, ctx: ServerCtx, conn_id: str, msg_id: int, payload: dict
    ):
        player: Player = payload['player']
        squares: int = payload['squares_per_row']
        target_len: int = payload['run_to_win']

        # TODO: handle validation of relative values of params
        game = GameModel(squares=squares, target_len=target_len)

        meta = GameMeta(
            state=GameState.JOIN_PENDING,
            player_nonces=(uuid.uuid4(), uuid.uuid4()),
            conn_ids=(conn_id, None) if player == 1 else (None, conn_id),
        )

        session_state, _ = await ctx.redis_store.read_session(conn_id)
        if session_state != SessionState.NEED_JOIN:
            log.msg('unexpected session state', session_state=session_state.value)

            await ctx.ws_manager.send_fatal(
                conn_id,
                wire.ServerMessage.build(
                    wire.ServerMsgType.ILLEGAL_MSG,
                    msg_id=0,  # TODO
                    error='session is not awaiting join',
                    err_msg_id=msg_id,
                ),
            )
            return

        game_key = await ctx.redis_store.put_game(game=game, meta=meta)
        await ctx.redis_store.put_session(
            conn_id, SessionState.NEED_JOIN_ACK, game_key.bytes
        )

        try:
            await ctx.ws_manager.send(
                conn_id,
                wire.ServerMessage.build(
                    wire.ServerMsgType.GAME_JOINED,
                    msg_id=0,  # TODO
                    player=player,
                    squares_per_row=squares,
                    run_to_win=target_len,
                    game_id=str(game_key),  # TODO
                    player_nonce=str(meta.get_player_nonce(player)),
                ),
            )
        except WebsocketConnectionLost:
            log.msg('connection lost')

            await asyncio.gather(
                ctx.redis_store.delete_game(game_key.bytes),
                ctx.redis_store.delete_session(conn_id),
            )

    @handler(wire.ClientMsgType.JOIN_GAME)
    @staticmethod
    async def on_join_game(
        *, log: Logger, ctx: ServerCtx, conn_id: str, msg_id: int, payload: dict
    ):
        game_id: str = payload['game_id']
        player: Player = payload['player']

        log = log.bind(game_id=game_id, player=player)

        game_id_bytes = uuid.UUID(game_id).bytes

        session_state, _ = await ctx.redis_store.read_session(conn_id)
        if session_state != SessionState.NEED_JOIN:
            log.msg('unexpected session state', session_state=session_state.value)

            await ctx.ws_manager.send_fatal(
                conn_id,
                wire.ServerMessage.build(
                    wire.ServerMsgType.ILLEGAL_MSG,
                    msg_id=0,  # TODO
                    error='session is not awaiting join',
                    err_msg_id=msg_id,
                ),
            )
            return

        meta = await ctx.redis_store.read_game_meta(game_id_bytes)

        if not await validate_join_request(ctx, log=log, player=player, meta=meta):
            log.msg('player already claimed')

            await ctx.ws_manager.send_fatal(
                conn_id,
                wire.ServerMessage.build(
                    wire.ServerMsgType.ILLEGAL_MSG,
                    msg_id=0,  # FIXME
                    error='player has already been claimed',
                    err_msg_id=msg_id,
                ),
            )
            return

        meta = meta.with_conn_id(player, conn_id)

        # TODO: validate state transitions?
        await asyncio.gather(
            ctx.redis_store.update_game(game_id_bytes, meta=meta),
            ctx.redis_store.put_session(
                conn_id, SessionState.NEED_JOIN_ACK, game_id_bytes
            ),
        )

        # XXX: org?
        _, game = await ctx.redis_store.read_game(game_id_bytes)

        try:
            await ctx.ws_manager.send(
                conn_id,
                wire.ServerMessage.build(
                    wire.ServerMsgType.GAME_JOINED,
                    msg_id=0,  # FIXME
                    game_id=game_id,
                    player=player,
                    player_nonce=str(meta.get_player_nonce(player)),
                    squares_per_row=game.squares,
                    run_to_win=game.target_len,
                ),
            )
        except WebsocketConnectionLost:
            log.msg('connection lost')

            # Roll back game updates...
            meta = meta.with_state(GameState.JOIN_PENDING).with_conn_id(player, None)
            await asyncio.gather(
                ctx.redis_store.delete_session(conn_id),
                ctx.redis_store.update_game(game_id_bytes, meta=meta),
            )

    @handler(wire.ClientMsgType.ACK_GAME_JOINED)
    @staticmethod
    async def on_ack_game_joined(
        *, log: Logger, ctx: ServerCtx, conn_id: str, msg_id: int, payload: dict
    ):
        session_state, game_id = await ctx.redis_store.read_session(conn_id)
        if session_state != SessionState.NEED_JOIN_ACK:
            log.msg('unexpected session state', session_state=session_state.value)

            await ctx.ws_manager.send_fatal(
                conn_id,
                wire.ServerMessage.build(
                    wire.ServerMsgType.ILLEGAL_MSG,
                    msg_id=0,  # FIXME
                    error='unexpected ack_game_joined',
                    err_msg_id=msg_id,
                ),
            )
            await ctx.redis_store.delete_session(conn_id)
            return

        assert game_id is not None
        meta = await ctx.redis_store.read_game_meta(game_id)

        for player in [Player(1), Player(2)]:
            if meta.get_conn_id(player) == conn_id:
                break
        else:
            log.msg('connection cleared from game')

            # shouldn't happen?
            await ctx.ws_manager.send_fatal(
                conn_id,
                wire.ServerMessage.build(
                    wire.ServerMsgType.ILLEGAL_MSG,
                    msg_id=0,  # FIXME
                    error='game cleared',
                    err_msg_id=msg_id,
                ),
            )
            await ctx.redis_store.delete_session(conn_id)
            return

        await ctx.redis_store.put_session(
            conn_id, state=SessionState.RUNNING, game_id=game_id
        )

        other_conn = meta.get_conn_id(get_opponent(player))

        if other_conn is None:
            all_joined = False
        else:
            other_state, _ = await ctx.redis_store.read_session(other_conn)
            all_joined = other_state == SessionState.RUNNING

        if all_joined:
            log.msg('game fully joined')

            meta = meta.with_state(GameState.RUNNING)
            await ctx.redis_store.update_game(game_id, meta=meta)

            _, game = await ctx.redis_store.read_game(game_id)
            await broadcast_game_state(ctx, meta, game)

    @handler(wire.ClientMsgType.REJOIN_GAME)
    @staticmethod
    async def on_rejoin_game(
        *, log: Logger, ctx: ServerCtx, conn_id: str, msg_id: int, payload: dict
    ):
        raise NotImplementedError('on rejoin game')

    # @handler(wire.ClientMsgType.NEW_MOVE)
    # async def on_new_move(*, log: Logger, ctx: ServerCtx, conn_id: str, payload: dict):
    #     pass


async def validate_join_request(
    ctx: ServerCtx, log: Logger, player: Player, meta: GameMeta
) -> bool:
    if meta.state != GameState.JOIN_PENDING:
        log.msg('game state is not pending join', game_state=meta.state.value)
        return False

    prior_conn_id = meta.get_conn_id(player)

    if prior_conn_id is None:
        return True

    prior_session_state, _ = await ctx.redis_store.read_session(prior_conn_id)

    if prior_session_state == SessionState.NEED_JOIN_ACK:
        # Clean up any connection which failed to ack its join before this request came in
        # FIXME: I don't really like this racing approach
        log.msg('tearing down prior connection', prior_conn_id=prior_conn_id)

        await asyncio.gather(
            ctx.redis_store.delete_session(prior_conn_id),
            ctx.ws_manager.close(prior_conn_id),
        )

        return True

    log.msg(
        'prior connection already joined',
        prior_conn_id=prior_conn_id,
        prior_session_state=prior_session_state.value,
    )
    return False


async def broadcast_game_state(ctx: ServerCtx, meta: GameMeta, game: GameModel) -> None:
    tasks = []
    for conn_id in meta.conn_ids:
        if conn_id is None:
            continue
        # FIXME: close handling
        tasks.append(
            ctx.ws_manager.send(
                conn_id,
                wire.ServerMessage.build(
                    wire.ServerMsgType.MOVE_PENDING,
                    msg_id=0,  # TODO
                    player=game.player,
                ),
            )
        )

    await asyncio.gather(*tasks)


#
# REDIS INTERFACE
#


class AbstractRedisStore(ABC):
    @abstractmethod
    async def put_session(
        self, conn_id: str, state: SessionState, game_id: Optional[bytes] = None
    ) -> None:
        """Write a new session into Redis"""
        raise NotImplementedError

    @abstractmethod
    async def read_session(self, conn_id: str) -> Tuple[SessionState, Optional[bytes]]:
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
    async def read_game_meta(self, key: bytes) -> GameMeta:
        raise NotImplementedError

    @abstractmethod
    async def delete_game(self, key: bytes):
        """Delete the given game from Redis"""
        raise NotImplementedError
