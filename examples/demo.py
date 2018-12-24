"""
Demo gameplay with random moves
"""
from __future__ import annotations

import asyncio
from random import randrange

from tact.game_model import Player, GameModel, GameOngoing, GameDrawn, Move
from tact.game_runner import BaseGameRunner, InMemoryGameRunner


async def run_player(gr: BaseGameRunner, player: Player):
    print('player', player, 'starting')

    if player == 1:
        print('sending first move')
        await gr.send_move(pick_move(gr.game))

    while True:
        print('player', player, 'waiting to move')
        _, game = await gr.opposing_move(player)

        if game.status() != GameOngoing:
            break

        print('picking move for', player)

        move = pick_move(game)
        assert move.player == player

        status = await gr.send_move(move)
        gr.game.dump_board()

        if status != GameOngoing:
            break

        print('move for', player, 'completed')


def pick_move(game: GameModel) -> Move:
    while True:
        x = randrange(game.squares)
        y = randrange(game.squares)

        if game.board[x][y] != None:
            continue

        return Move(player=game.player, coords=(x, y))


async def main():
    print('Starting...')
    gr = InMemoryGameRunner(squares=8, target_len=5)

    print('Running players...')

    await asyncio.gather(
        run_player(gr, 1),
        run_player(gr, 2),
    )

    status = gr.game.status()
    if status == GameDrawn:
        print('Draw')
    else:
        print('Winner is', status)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()
