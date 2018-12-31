from __future__ import annotations

import enum
import json
import asyncio
from typing import Awaitable, Dict, Optional

import websockets as ws

from ..networking.wire import ClientMessage, ClientMsgType, ServerMessage, ServerMsgType
from ..networking.handlers import handler_set, handler
from ..game_model import GameModel, Move, Player


class ClientConnectionState(enum.Enum):
    INIT = 'init'
    JOIN_PENDING = 'join-pending'
    GAME_START_PENDING = 'game-start-pending'
    GAME_RUNNING = 'game-running'
    GAME_COMPLETE = 'game-complete'


class ClientConnection:
    """Client server connection"""

    def __init__(self, server_url: str) -> None:
        self.server_url = server_url

        self._handlers = handler_set(self)

        self._socket: Optional[ws.WebSocketClientProtocol] = None
        self._pending_connect: Optional[Awaitable[ws.WebSocketClientProtocol]] = None

        self._msg_id = 0
        self._state = ClientConnectionState.INIT
        self._state_futures: Dict[ClientConnectionState, asyncio.Future[None]] = {}

        self._player: Optional[Player] = None
        self._game_id: Optional[str] = None
        self._nonce: Optional[str] = None
        self._game_model: Optional[GameModel] = None

    # Client-initiated messaging

    async def new_game(self, player: Player, squares: int, target_len: int) -> None:
        self._chkstate(ClientConnectionState.INIT)

        self._player = player
        self._game_model = GameModel(squares=squares, target_len=target_len)

        msg = ClientMessage.build(
            ClientMsgType.NEW_GAME,
            msg_id=self._new_msg(),
            player=player,
            squares_per_row=squares,
            run_to_win=target_len,
        )

        self._set_state(ClientConnectionState.JOIN_PENDING)
        await self._send(json.dumps(msg))

    async def join(self, player: Player, game_id: str) -> None:
        self._chkstate(ClientConnectionState.INIT)

        self._player = player
        self._game_id = game_id

        msg = ClientMessage.build(
            ClientMsgType.JOIN_GAME,
            msg_id=self._new_msg(),
            game_id=game_id,
            player=player,
        )

        self._set_state(ClientConnectionState.JOIN_PENDING)
        await self._send(json.dumps(msg))

    async def send_move(self, move: Move):
        self._chkstate(ClientConnectionState.GAME_RUNNING)

        raise NotImplementedError
        msg = ClientMessage.build(
            ClientMsgType.NEW_MOVE,
            msg_id=self._new_msg(),
            game_id=self._game_id,
            player=move.player,
            x=move.x,
            y=move.y,
        )
        self._send(json.dumps(msg))

    # def send_err(self, msg):
    #     pass

    def _new_msg(self) -> int:
        msg_id = self._msg_id
        self._msg_id += 1
        return msg_id

    async def _send(self, msg: str) -> None:
        await self._connect()

        print('send', msg)

        socket: ws.WebSocketClientProtocol = self._socket
        await socket.send(msg)

        print('...sent')

        # FIXME: wrong
        await self._inbound()

    async def _connect(self) -> None:
        if self._socket:
            return

        if self._pending_connect:
            await self._pending_connect
            return

        self._pending_connect = connecting = ws.connect(self.server_url)
        try:
            self._socket = await connecting
        finally:
            self._pending_connect = None

        # self._inbound()

    async def _inbound(self) -> None:
        """Receive and process incoming messages on a socket

        Must be reinvoked if the WebSocket connection goes down.
        """
        socket: ws.WebSocketClientProtocol = self._socket
        async for msg in socket:
            print('recv:', msg)
            self._handle_inbound(msg)

    def _handle_inbound(self, msg_src: str) -> None:
        # TODO: Error handling
        msg = json.loads(msg_src)
        msg_type, payload = ServerMessage.parse(msg)
        self._handlers.dispatch(msg_type, msg_id=msg['msg_id'], payload=payload)

    # State-change management

    async def wait_for_state(self, state: ClientConnectionState) -> None:
        if self._state == state:
            return

        if state not in self._state_futures:
            self._state_futures[state] = asyncio.Future()

        await self._state_futures[state]

    async def opposing_move(self, player: Player) -> Move:
        await self.wait_for_state(ClientConnectionState.GAME_RUNNING)
        raise NotImplementedError

    def _chkstate(self, state: ClientConnectionState) -> None:
        if state != self._state:
            raise RuntimeError(
                f'illegal client connection state {self._state.value} '
                f'(expected {state.value})'
            )

    def _set_state(self, state: ClientConnectionState) -> None:
        self._state = state

        if state in self._state_futures:
            self._state_futures[state].set_result(None)
            del self._state_futures[state]

    def game_id(self) -> str:
        if self._game_id is None:
            raise RuntimeError('Game join is not complete')

        return self._game_id

    # Message handlers

    @handler(ServerMsgType.ILLEGAL_MSG)
    def on_illegal_msg(self, msg_id, payload) -> None:
        self._abort_game()

    @handler(ServerMsgType.ILLEGAL_MOVE)
    def on_illegal_move(self, msg_id, payload) -> None:
        self._abort_game()

    def _abort_game(self) -> None:
        # TODO: More?
        self._set_state(ClientConnectionState.GAME_COMPLETE)

    @handler(ServerMsgType.GAME_JOINED)
    def on_game_joined(self, msg_id, payload) -> None:
        self._chkstate(ClientConnectionState.JOIN_PENDING)

        self._player: Optional[Player] = None
        self._game_id: Optional[str] = None
        self._nonce: Optional[str] = None
        self._game_model: Optional[GameModel] = None

        self._nonce = payload['player_nonce']
        self._game_id = payload['game_id']

        self._set_state(ClientConnectionState.GAME_RUNNING)

    @handler(ServerMsgType.MOVE_PENDING)
    def on_move_pending(self, msg_id, payload) -> None:
        if self._state == ClientConnectionState.GAME_START_PENDING:
            self._set_state(ClientConnectionState.GAME_RUNNING)
        else:
            self._chkstate(ClientConnectionState.GAME_RUNNING)

        # TODO: Callback
        raise NotImplementedError

    @handler(ServerMsgType.GAME_OVER)
    def on_game_over(self, msg_id, payload) -> None:
        self._chkstate(ClientConnectionState.GAME_RUNNING)
        self._set_state(ClientConnectionState.GAME_COMPLETE)

        # TODO: Callback
        raise NotImplementedError
