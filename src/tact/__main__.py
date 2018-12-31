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

    args = parser.parse_args()

    cmd_handlers = {'serve': serve}

    try:
        cmd_handlers[args.cmd]()
    except Exception as exc:  # pylint: disable=broad-except
        parser.exit(status=1, message=f'error: {exc}')


if __name__ == '__main__':
    main()
