"""Base definitions for the websocket interface"""
import json
from abc import ABC, abstractmethod


class WebsocketConnectionLost(Exception):
    pass


class AbstractWSManager(ABC):
    @abstractmethod
    async def send(self, conn_id: str, msg: dict) -> None:
        # This is implemented as a separate method primarily for test
        # convenience
        serialized = json.dumps(msg, separators=(',', ':'))
        await self._send_serialized(conn_id, serialized)

    @abstractmethod
    async def _send_serialized(self, conn_id: str, msg: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self, conn_id: str):
        raise NotImplementedError
