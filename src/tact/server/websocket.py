from abc import ABC, abstractmethod


class WebsocketConnectionLost(Exception):
    pass


class AbstractWSManager(ABC):
    @abstractmethod
    async def send(self, conn_id: str, msg: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self, conn_id: str):
        raise NotImplementedError
