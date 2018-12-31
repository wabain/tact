from __future__ import annotations

import os
import asyncio
import argparse
from types import SimpleNamespace
from typing import List


def serve():
    from tact.server.local_server import listen
    from tact.server.redis_store import RedisStore

    env = load_from_env(['PORT', 'REDIS_URL'])

    addr = ('0.0.0.0', env.PORT)
    redis_store = RedisStore(url=env.REDIS_URL)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(listen(addr, redis_store))


def run_client(squares: int, target_len: int, server_url: str, verbose: bool):
    from tact.agent.random import RandomAgent
    from tact.game_runner import launch_game
    from tact.client.networked_game_runner import NetworkedGameRunner

    runner = NetworkedGameRunner(
        squares=squares, target_len=target_len, server_url=server_url
    )

    game = launch_game(
        runner, agents=[RandomAgent(player=1), RandomAgent(player=2)], verbose=verbose
    )

    if not verbose:
        game.dump_board()

    print('Result:', game.status().name)


def load_from_env(keys: List[str]) -> SimpleNamespace:
    items = [(key, os.environ.get(key)) for key in keys]
    missing = [k for k, v in items if v is None]

    if missing:
        raise ValueError(
            'Missing required environment variables: ' + ', '.join(missing)
        )

    return SimpleNamespace(**dict(items))


def main():
    parser = argparse.ArgumentParser('tact')

    subcmds = parser.add_subparsers(dest='cmd', required=True)

    _serve_parser = subcmds.add_parser('serve', help='Run a local server')

    client_parser = subcmds.add_parser('join')
    client_parser.add_argument('--squares-per-row', type=int, default=8)
    client_parser.add_argument('--row-to-win', type=int, default=5)
    client_parser.add_argument('server_url')
    client_parser.add_argument('--verbose', action='store_true')

    args = parser.parse_args()

    cmd_handlers = {
        'serve': serve,
        'join': lambda: run_client(
            squares=args.squares_per_row,
            target_len=args.row_to_win,
            server_url=args.server_url,
            verbose=args.verbose,
        ),
    }

    try:
        cmd_handlers[args.cmd]()
    except Exception as exc:  # pylint: disable=broad-except
        parser.exit(status=1, message=f'error: {exc}')


if __name__ == '__main__':
    main()
