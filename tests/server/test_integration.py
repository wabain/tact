"""Simple integration tests which exercise the server functionality

The server is backed by Redis, with client logic driven by the test script.
"""

from __future__ import annotations

from typing import Dict
import json
import asyncio

import pytest

from tact.networking import wire
from tact.server import server
from tact.server.redis_store import RedisStore
from tact.server.websocket import WebsocketConnectionLost, AbstractWSManager

# XXX
from tests.server.test_redis_store import (  # pylint: disable=unused-import
    redis_test_db_init,
    store,
)


@pytest.mark.asyncio
async def test_simple_game(store: RedisStore):  # pylint: disable=redefined-outer-name
    mgr = InMemoryWSManager()
    ctx = server.ServerCtx(redis_store=store, ws_manager=mgr)

    client1 = await mgr.open(ctx)
    client2 = await mgr.open(ctx)

    await mgr.client_send(
        ctx,
        client1.conn_id,
        json.dumps(
            wire.ClientMessage.build(
                wire.ClientMsgType.NEW_GAME,
                msg_id=0,
                player=1,
                squares_per_row=8,
                run_to_win=5,
            )
        ),
    )

    msg_type, msg_id, payload = await client1.recv()

    assert msg_type == wire.ServerMsgType.GAME_JOINED
    assert msg_id == 0
    assert payload['player'] == 1
    assert payload['squares_per_row'] == 8
    assert payload['run_to_win'] == 5

    game_id = payload['game_id']
    _p1_nonce = payload['player_nonce']

    await mgr.client_send(
        ctx,
        client2.conn_id,
        json.dumps(
            wire.ClientMessage.build(
                wire.ClientMsgType.JOIN_GAME, msg_id=0, game_id=game_id, player=2
            )
        ),
    )

    msg_type, msg_id, payload = await client2.recv()

    assert msg_type == wire.ServerMsgType.GAME_JOINED
    assert msg_id == 0
    assert payload['player'] == 2
    assert payload['squares_per_row'] == 8
    assert payload['run_to_win'] == 5

    _p2_nonce = payload['player_nonce']

    for client in [client1, client2]:
        await mgr.client_send(
            ctx,
            client.conn_id,
            json.dumps(
                wire.ClientMessage.build(wire.ClientMsgType.ACK_GAME_JOINED, msg_id=0)
            ),
        )

    for client in [client1, client2]:
        await client.assert_recv(wire.ServerMsgType.MOVE_PENDING, 0, dict(player=1))


class InMemoryWSClient:
    def __init__(self, conn_id: str):
        self.conn_id = conn_id
        self._inbound = asyncio.Queue()

    async def handle(self, msg: str):
        parsed = wire.ServerMessage.parse(json.loads(msg))
        print(parsed)
        await self._inbound.put(parsed)

    async def recv(self):
        return await asyncio.wait_for(self._inbound.get(), 1)

    async def assert_recv(self, msg_type, msg_id=None, payload=None):
        act_msg_type, act_msg_id, act_payload = await self.recv()
        assert act_msg_type == msg_type
        if msg_id is not None:
            assert act_msg_id == msg_id
        assert act_payload == payload


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
            del self._clients[conn_id]
        except KeyError:
            pass

        # TODO: Notify server

    def _get_client(self, conn_id: str) -> InMemoryWSClient:
        try:
            return self._clients[conn_id]
        except KeyError:
            raise WebsocketConnectionLost(conn_id)
