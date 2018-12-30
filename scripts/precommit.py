#!/usr/bin/env python3

import argparse
import sys
from subprocess import call


MIN_PY_VERSION = (3, 7)


def main() -> None:
    if sys.version_info < MIN_PY_VERSION:
        raise RuntimeError(
            'Unsupported python version: Can only run in development virtualenv'
        )

    parser = argparse.ArgumentParser()
    parser.add_argument('--test', help='Only run testing steps', action='store_true')
    parser.add_argument('--lint', help='Only run linting steps', action='store_true')
    parser.add_argument(
        '--fix', help='Fix issues automatically where possible', action='store_true'
    )

    args = parser.parse_args()

    all_phases = not args.lint and not args.test
    res = exec_precommit(
        test=(args.test or all_phases), lint=(args.lint or all_phases), fix=args.fix
    )
    sys.exit(res)


def exec_precommit(*, test: bool, lint: bool, fix: bool) -> int:
    steps = []

    if test:
        steps.append('python setup.py test')

    if lint:
        black_args = '' if fix else '--diff --check '
        steps.extend(
            [
                f'black {black_args}setup.py src tests',
                'mypy --ignore-missing-imports src tests',
                'pylint setup.py tact tests/*',
            ]
        )

    results = []

    for i, cmd in enumerate(steps, start=1):
        print(f'{i}/{len(steps)}:', cmd)

        res = call(cmd, shell=True)
        results.append(res)

        print()

    overall = max(results)

    print()
    print(get_mark(overall), 'Success' if overall == 0 else 'Failed')
    print()

    for i, (cmd, res) in enumerate(zip(steps, results), start=1):
        res_out = '    ' if res == 0 else f'({res})'
        print(f'{get_mark(res)} {res_out: <4}{i}/{len(steps)}:', cmd)

    return overall


def get_mark(retcode: int) -> str:
    return '✨' if retcode == 0 else '❌'


if __name__ == '__main__':
    main()
