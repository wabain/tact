from __future__ import annotations

import asyncio
from typing import Dict, Tuple, Optional

from ..game_model import GameModel, Move, Player
from ..game_runner import AbstractGameRunner
from .connection import ClientConnection, ClientConnectionState


class NetworkedGameRunner(AbstractGameRunner):
    def __init__(self, *, squares: int, target_len: int, server_url: str) -> None:
        self.squares = squares
        self.target_len = target_len
        self.server_url = server_url

        self._game = GameModel(squares=squares, target_len=target_len)

        self._connections: Dict[Player, ClientConnection] = {}

        self._initializing_player: Optional[Player] = None
        self._game_id: Optional[str] = None

    async def claim_player(self, player: Player) -> None:
        if player in self._connections:
            raise RuntimeError(f'Player {player} already claimed')

        conn = ClientConnection(self.server_url)

        # TODO: need to be able to join remotely initiated game
        if not self._connections:
            await conn.new_game(
                player, squares=self.squares, target_len=self.target_len
            )
            self._initializing_player = player
        else:
            assert self._initializing_player is not None
            new_game_conn = self._connections[self._initializing_player]
            await new_game_conn.wait_for_state(ClientConnectionState.GAME_START_PENDING)

            await conn.join(player, game_id=new_game_conn.game_id())

        self._connections[player] = conn

    async def launch(self) -> None:
        if not self._connections:
            raise RuntimeError('cannot launch game with no agents registered')

        client_games_running = [
            c.wait_for_state(ClientConnectionState.GAME_RUNNING)
            for c in self._connections.values()
        ]

        await asyncio.gather(*client_games_running)

    async def send_move(self, move: Move) -> GameModel:
        if move.player not in self._connections:
            raise RuntimeError(f'Player {move.player} is not being managed locally')

        self._game.apply_move(move)
        await self._connections[move.player].send_move(move)

        return self._game.copy()

    async def opposing_move(self, player: Player) -> Tuple[Move, GameModel]:
        move = await self._connections[player].opposing_move(player)
        game = await self.game()  # XXX?
        return move, game

    async def game(self) -> GameModel:
        return self._game.copy()
