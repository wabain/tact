from __future__ import annotations
from typing import Generic, TypeVar


T = TypeVar('T')


class HandlerSet(Generic[T]):
    def __init_subclass__(cls):
        super().__init_subclass__()

        handlers = {}
        for v in cls.__dict__.values():
            if hasattr(v, '_handler_key'):
                handlers[v._handler_key] = v
        cls.handlers = handlers

    @classmethod
    def dispatch(cls, value: T, *args, **kwargs):
        if not hasattr(cls, 'handlers'):
            raise TypeError('incorrectly invoked subclass of HandlerSet')
        return cls.handlers[value](*args, **kwargs)


def handler(key):
    def bind_handler(fn):
        fn._handler_key = key
        return fn

    return bind_handler
