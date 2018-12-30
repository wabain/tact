"""Support for a development server which can be run locally.

This is needed since there is currently limited support for emulating API
Gateway's websocket support.
"""
from __future__ import annotations

from typing import Dict, Tuple

import websockets as ws

from .websocket import AbstractWSManager
from . import server


async def listen(bind: Tuple[str, int], redis_store: server.AbstractRedisStore) -> None:
    manager = LocalWSManager(redis_store=redis_store)

    addr, port = bind
    srv = await ws.serve(manager.handle_conn, addr, port)
    await srv.wait_closed()


class LocalWSManager(AbstractWSManager):
    def __init__(self, redis_store: server.AbstractRedisStore) -> None:
        self._redis_store = redis_store
        self._conn_idx = 0
        self._conns: Dict[str, ws.WebSocketServerProtocol] = {}

    async def handle_conn(
        self,
        socket: ws.WebSocketServerProtocol,
        path: str,  # pylint: disable=unused-argument
    ) -> None:
        # TODO: what to do with path?

        conn_id = self._new_conn_id()
        self._conns[conn_id] = socket

        ctx = server.ServerCtx(redis_store=self._redis_store, ws_manager=self)

        try:
            await server.new_connection(ctx=ctx, conn_id=conn_id)

            async for msg in socket:
                await server.new_message(ctx=ctx, conn_id=conn_id, msg_src=msg)

            # TODO: server close handler?
        finally:
            del self._conns[conn_id]

    async def send(self, conn_id: str, msg: dict) -> None:
        await super().send(conn_id, msg)

    async def _send_serialized(self, conn_id: str, msg: str) -> None:
        await self._conns[conn_id].send(msg)

    async def close(self, conn_id: str):
        await self._conns[conn_id].close()

    def _new_conn_id(self) -> str:
        conn_id = self._conn_idx
        self._conn_idx += 1
        return str(conn_id)
