"""Simple integration tests which exercise the server functionality

The server is backed by Redis, with client logic driven by the test script.
"""

from __future__ import annotations

from typing import Dict
import json
import asyncio
from itertools import cycle

from structlog import get_logger
import pytest

from tact.game_model import Player, get_opponent
from tact.networking import wire
from tact.server import server
from tact.server.redis_store import RedisStore
from tact.server.websocket import WebsocketConnectionLost, AbstractWSManager

# XXX
from tests.server.test_redis_store import (  # pylint: disable=unused-import
    redis_test_db_init,
    store,
)


logger = get_logger()  # pylint: disable=invalid-name


@pytest.mark.asyncio
async def test_multi_join_pre_ack(
    store: RedisStore
):  # pylint: disable=redefined-outer-name
    mgr = InMemoryWSManager()
    ctx = server.ServerCtx(redis_store=store, ws_manager=mgr)

    # Setup: client 1 starts new game
    client1 = await mgr.open(ctx)

    await client1.send(
        ctx, wire.ClientMsgType.NEW_GAME, player=1, squares_per_row=8, run_to_win=5
    )
    _, _, payload = await client1.assert_recv(wire.ServerMsgType.GAME_JOINED)
    game_id = payload['game_id']

    # Two client instances join the game, before either acks
    client2a = await mgr.open(ctx)
    await client2a.send(ctx, wire.ClientMsgType.JOIN_GAME, game_id=game_id, player=2)
    _, _, client2a_join = await client2a.assert_recv(wire.ServerMsgType.GAME_JOINED)

    client2b = await mgr.open(ctx)
    await client2b.send(ctx, wire.ClientMsgType.JOIN_GAME, game_id=game_id, player=2)
    _, _, client2b_join = await client2b.assert_recv(wire.ServerMsgType.GAME_JOINED)

    assert client2a_join['game_id'] == game_id
    assert client2a_join['player'] == 2
    assert client2b_join['game_id'] == game_id
    assert client2b_join['player'] == 2
    assert client2a_join['player_nonce'] == client2b_join['player_nonce']

    assert (
        client2a.closed
    ), 'session should be closed when another pre-ack join request comes in'

    # Clients 1 and 2b ack the join, and the game can begin
    await client2b.send(ctx, wire.ClientMsgType.ACK_GAME_JOINED)
    await client1.send(ctx, wire.ClientMsgType.ACK_GAME_JOINED)

    await client1.assert_recv(
        wire.ServerMsgType.MOVE_PENDING, payload={'player': 1, 'last_move': None}
    )
    await client2b.assert_recv(
        wire.ServerMsgType.MOVE_PENDING, payload={'player': 1, 'last_move': None}
    )


@pytest.mark.asyncio
async def test_multi_join_post_ack(
    store: RedisStore
):  # pylint: disable=redefined-outer-name
    mgr = InMemoryWSManager()
    ctx = server.ServerCtx(redis_store=store, ws_manager=mgr)

    # Setup: client 1 starts new game
    client1 = await mgr.open(ctx)

    await client1.send(
        ctx, wire.ClientMsgType.NEW_GAME, player=1, squares_per_row=8, run_to_win=5
    )
    _, _, payload = await client1.assert_recv(wire.ServerMsgType.GAME_JOINED)
    game_id = payload['game_id']

    # A client instance joins the game and sends an ack
    client2a = await mgr.open(ctx)
    await client2a.send(ctx, wire.ClientMsgType.JOIN_GAME, game_id=game_id, player=2)
    _, _, client2a_join = await client2a.assert_recv(wire.ServerMsgType.GAME_JOINED)

    assert client2a_join['game_id'] == game_id
    assert client2a_join['player'] == 2

    await client2a.send(ctx, wire.ClientMsgType.ACK_GAME_JOINED)

    # Another client instance tries to join, post-ack
    await _try_illegal_join_post_ack(ctx, game_id=game_id, player=Player(2))

    # Client 1 acks the join, and the game can begin
    await client1.send(ctx, wire.ClientMsgType.ACK_GAME_JOINED)

    await client1.assert_recv(
        wire.ServerMsgType.MOVE_PENDING, payload={'player': 1, 'last_move': None}
    )
    await client2a.assert_recv(
        wire.ServerMsgType.MOVE_PENDING, payload={'player': 1, 'last_move': None}
    )

    # Another client instance tries to join, with the game running
    await _try_illegal_join_post_ack(ctx, game_id=game_id, player=Player(2))


async def _try_illegal_join_post_ack(
    ctx: server.ServerCtx, game_id: str, player: Player
) -> None:
    mgr: InMemoryWSManager = ctx.ws_manager
    client = await mgr.open(ctx)
    illegal_join_msg_id = client.msg_id
    await client.send(ctx, wire.ClientMsgType.JOIN_GAME, game_id=game_id, player=player)
    await client.assert_recv(
        wire.ServerMsgType.ILLEGAL_MSG,
        payload={
            'error': 'player has already been claimed',
            'err_msg_id': illegal_join_msg_id,
        },
    )
    assert client.closed


@pytest.mark.asyncio
async def test_rejoin_prior_game_running(
    store: RedisStore
):  # pylint: disable=redefined-outer-name
    mgr = InMemoryWSManager()
    ctx = server.ServerCtx(redis_store=store, ws_manager=mgr)

    # Setup: client 1 starts new game
    client1a = await mgr.open(ctx)

    await client1a.send(
        ctx, wire.ClientMsgType.NEW_GAME, player=1, squares_per_row=8, run_to_win=5
    )
    _, _, payload = await client1a.assert_recv(wire.ServerMsgType.GAME_JOINED)
    game_id = payload['game_id']
    player_nonce = payload['player_nonce']

    await client1a.send(ctx, wire.ClientMsgType.ACK_GAME_JOINED)

    # Client 1 reconnects over a new session
    client1b = await mgr.open(ctx)
    await client1b.send(
        ctx,
        wire.ClientMsgType.REJOIN_GAME,
        game_id=game_id,
        player=1,
        player_nonce=str(player_nonce),
    )

    assert client1a.closed

    # Client 2 joins
    client2 = await mgr.open(ctx)
    await client2.send(ctx, wire.ClientMsgType.JOIN_GAME, game_id=game_id, player=2)
    await client2.assert_recv(wire.ServerMsgType.GAME_JOINED)
    await client2.send(ctx, wire.ClientMsgType.ACK_GAME_JOINED)

    # Verify that game advances
    await client1b.assert_recv(wire.ServerMsgType.MOVE_PENDING)
    await client2.assert_recv(wire.ServerMsgType.MOVE_PENDING)


@pytest.mark.asyncio
async def test_rejoin_after_game_start(
    store: RedisStore
):  # pylint: disable=redefined-outer-name
    mgr = InMemoryWSManager()
    ctx = server.ServerCtx(redis_store=store, ws_manager=mgr)

    # Setup: client 1 starts new game
    client1a = await mgr.open(ctx)

    await client1a.send(
        ctx, wire.ClientMsgType.NEW_GAME, player=1, squares_per_row=8, run_to_win=5
    )
    _, _, payload = await client1a.assert_recv(wire.ServerMsgType.GAME_JOINED)
    game_id = payload['game_id']
    player_nonce = payload['player_nonce']

    await client1a.send(ctx, wire.ClientMsgType.ACK_GAME_JOINED)

    # Client 2 joins
    client2 = await mgr.open(ctx)
    await client2.send(ctx, wire.ClientMsgType.JOIN_GAME, game_id=game_id, player=2)
    await client2.assert_recv(wire.ServerMsgType.GAME_JOINED)
    await client2.send(ctx, wire.ClientMsgType.ACK_GAME_JOINED)

    # Verify that game advances
    await client1a.assert_recv(wire.ServerMsgType.MOVE_PENDING)
    await client2.assert_recv(wire.ServerMsgType.MOVE_PENDING)

    # Client 1 reconnects over a new session
    client1b = await mgr.open(ctx)
    await client1b.send(
        ctx,
        wire.ClientMsgType.REJOIN_GAME,
        game_id=game_id,
        player=1,
        player_nonce=str(player_nonce),
    )

    assert client1a.closed
    await client1b.assert_recv(wire.ServerMsgType.MOVE_PENDING)


@pytest.mark.asyncio
async def test_simple_game(store: RedisStore):  # pylint: disable=redefined-outer-name
    mgr = InMemoryWSManager()
    ctx = server.ServerCtx(redis_store=store, ws_manager=mgr)

    client1 = await mgr.open(ctx)
    client2 = await mgr.open(ctx)

    await client1.send(
        ctx, wire.ClientMsgType.NEW_GAME, player=1, squares_per_row=3, run_to_win=3
    )

    _, _, payload = await client1.assert_recv(wire.ServerMsgType.GAME_JOINED)

    assert payload['player'] == 1
    assert payload['squares_per_row'] == 3
    assert payload['run_to_win'] == 3

    game_id = payload['game_id']

    await client2.send(ctx, wire.ClientMsgType.JOIN_GAME, game_id=game_id, player=2)

    _, _, payload = await client2.assert_recv(wire.ServerMsgType.GAME_JOINED)

    assert payload['player'] == 2
    assert payload['squares_per_row'] == 3
    assert payload['run_to_win'] == 3

    for client in [client1, client2]:
        await client.send(ctx, wire.ClientMsgType.ACK_GAME_JOINED)

    for client in [client1, client2]:
        await client.assert_recv(
            msg_type=wire.ServerMsgType.MOVE_PENDING,
            payload={'player': 1, 'last_move': None},
        )

    moves = [
        # fmt: off
        (0, 0),
        (1, 1),

        (2, 0),
        (1, 0),

        (1, 2),
        (2, 1),

        (0, 1),
        (0, 2),
    ]

    for i, (client, (x, y)) in enumerate(zip(cycle([client1, client2]), moves)):
        await client.send(ctx, wire.ClientMsgType.NEW_MOVE, x=x, y=y)

        if i == len(moves) - 1:
            expected = {
                'msg_type': wire.ServerMsgType.GAME_OVER,
                'payload': {
                    'winner': None,
                    'is_draw': True,
                    'is_technical_forfeit': False,
                    'is_user_forfeit': False,
                },
            }
        else:
            player = 2 if i % 2 == 0 else 1
            expected = {
                'msg_type': wire.ServerMsgType.MOVE_PENDING,
                'payload': {
                    'player': player,
                    'last_move': {'x': x, 'y': y, 'player': get_opponent(player)},
                },
            }

        await client1.assert_recv(**expected)
        await client2.assert_recv(**expected)


class InMemoryWSClient:
    def __init__(self, conn_id: str):
        self.conn_id = conn_id
        self.msg_id = 1
        self.last_server_msg_id = 0
        self.closed = False
        self._inbound = asyncio.Queue()

    async def send(
        self,
        ctx: server.ServerCtx,
        msg_type: wire.ClientMsgType,
        *,
        msg_id=None,
        **payload,
    ) -> None:
        if msg_id is None:
            msg_id = self.msg_id
            self.msg_id += 1
        else:
            self.msg_id = msg_id + 1

        mgr: InMemoryWSManager = ctx.ws_manager

        logger.msg(
            'InMemoryWSClient: send',
            conn_id=self.conn_id,
            msg_type=msg_type.value,
            msg_id=msg_id,
            payload=payload,
        )

        await mgr.client_send(
            ctx,
            self.conn_id,
            json.dumps(wire.ClientMessage.build(msg_type, msg_id=msg_id, **payload)),
        )

    async def handle(self, msg: str):
        parsed = wire.ServerMessage.parse(json.loads(msg))

        msg_type, msg_id, payload = parsed
        logger.msg(
            'InMemoryWSClient: parsed',
            conn_id=self.conn_id,
            msg_type=msg_type.value,
            msg_id=msg_id,
            payload=payload,
        )

        await self._inbound.put(parsed)

    async def recv(self):
        return await asyncio.wait_for(self._inbound.get(), 1)

    async def assert_recv(self, msg_type, msg_id=None, payload=None):
        act_msg_type, act_msg_id, act_payload = await self.recv()

        assert act_msg_type == msg_type

        if msg_id is None:
            msg_id = self.last_server_msg_id + 1

        self.last_server_msg_id = act_msg_id

        assert act_msg_id == msg_id

        if payload is not None:
            assert act_payload == payload
        return act_msg_type, act_msg_id, act_payload


class InMemoryWSManager(AbstractWSManager):
    def __init__(self):
        self._client_idx = 0
        self._clients: Dict[InMemoryWSClient] = {}

    async def open(self, ctx: server.ServerCtx) -> InMemoryWSClient:
        self._client_idx += 1
        client_id = str(self._client_idx)
        client = InMemoryWSClient(client_id)
        self._clients[client_id] = client

        await server.new_connection(ctx, client_id)
        return client

    async def client_send(self, ctx: server.ServerCtx, conn_id: str, msg: str) -> None:
        await server.new_message(ctx, conn_id, msg)

    async def send(self, conn_id: str, msg: str) -> None:
        await super().send(conn_id, msg)

    async def _send_serialized(self, conn_id: str, msg: str) -> None:
        client = self._get_client(conn_id)
        try:
            await client.handle(msg)
        except Exception as exc:
            raise RuntimeError('exception from client handler') from exc

    async def close(self, conn_id: str) -> None:
        try:
            client = self._clients[conn_id]
        except KeyError:
            pass

        client.closed = True
        del self._clients[conn_id]

        # TODO: Notify server

    def _get_client(self, conn_id: str) -> InMemoryWSClient:
        try:
            return self._clients[conn_id]
        except KeyError:
            raise WebsocketConnectionLost(conn_id)
