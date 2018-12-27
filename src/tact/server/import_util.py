from contextlib import contextmanager


@contextmanager
def try_server_imports():
    try:
        yield
    except ImportError:
        raise ImportError(
            'server dependencies not installed; try installing with the server '
            'extra installs: pip install "tact[server]"'
        )
