# pylint: disable=invalid-name

import pytest

from tact.networking.handlers import (
    handler,
    handler_set,
    build_dispatch_table,
    HandlerSet,
)

# Handler base classes establish subclass hooks without defining methods
# locally
# pylint: disable=too-few-public-methods


def test_handler_set():
    class H(HandlerSet):
        @handler(1)
        @staticmethod
        def x(a):
            return a + 1

        @handler(2)
        @staticmethod
        def y(a):
            return a + 2

    assert H.dispatch(1, 1) == 2
    assert H.dispatch(2, 1) == 3

    with pytest.raises(ValueError):
        H.dispatch(3, 1)


def test_delegated_handler_set():
    class Delegate:
        def __init__(self, n):
            self.n = n

        @handler(1)
        def x(self, a):
            return self.n + a + 1

        @handler(2)
        def y(self, a):
            return self.n + a + 2

    delegate = Delegate(n=50)
    dispatch_table = build_dispatch_table(delegate)  # pylint: disable=unused-variable

    class H(HandlerSet, handlers=dispatch_table):
        pass

    assert H.dispatch(1, 1) == 52, 'static delegated handler set'
    assert H.dispatch(2, 1) == 53, 'static delegated handler set'

    dyn_handlers = handler_set(delegate)

    assert dyn_handlers.dispatch(1, 1) == 52, 'dynamic delegated handler set'
    assert dyn_handlers.dispatch(2, 1) == 53, 'dynamic delegated handler set'


def test_handler_set_base_invocation():
    with pytest.raises(TypeError):
        HandlerSet.dispatch(1, 0)
