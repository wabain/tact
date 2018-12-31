"""Utilities for handler declaration

Allows declaring handlers for a set up of input values using decorators on methods
of a subclass of HandlerSet, which defines a `dispatch` method which calls the
appropriate handler based on the value of the first argument.

TODO
====

1. See if uses of this class could be replaced by functools.singledispatch or
   a similar implementation.
2. Otherwise, document handler delegation
"""
from __future__ import annotations
from typing import Any, Dict, Generic, TypeVar
import inspect

# Handler base classes establish subclass hooks without defining methods
# locally
# pylint: disable=too-few-public-methods


def handler(key):
    def bind_handler(func):
        func._handler_key = key  # pylint: disable=protected-access
        return func

    return bind_handler


T = TypeVar('T')


class HandlerSet(Generic[T]):
    def __init_subclass__(cls, handlers=None):
        super().__init_subclass__()
        if handlers is None:
            handlers = build_dispatch_table(cls)
        cls.handlers = handlers

    @classmethod
    def dispatch(cls, value: T, *args, **kwargs):
        if not hasattr(cls, 'handlers'):
            raise TypeError('incorrectly invoked subclass of HandlerSet')

        try:
            hdl = cls.handlers[value]
        except KeyError:
            raise ValueError(f'Failed to look up handler for {value}')

        return hdl(*args, **kwargs)


def handler_set(obj: object):
    # pylint doesn't understand variable use in class init
    dispatch_table = build_dispatch_table(obj)  # pylint: disable=unused-variable

    class HandlerSetImpl(HandlerSet, handlers=dispatch_table):
        pass

    return HandlerSetImpl


def build_dispatch_table(obj: object) -> Dict[Any, Any]:
    handlers = {}

    for member, candidates in get_candidates_for_members(obj):
        for candidate in candidates:
            if not has_handler_key(candidate):
                continue

            handlers[get_handler_key(candidate)] = member

    return handlers


def get_candidates_for_members(obj):
    if isinstance(obj, type):
        for k, v in obj.__dict__.items():
            yield getattr(obj, k), _get_class_member_candidates(obj, k, v)

        return

    for _, v in inspect.getmembers(obj):
        yield v, _get_instance_member_candidates(v)


def _get_class_member_candidates(obj, k, v):
    yield inspect.unwrap(v, stop=has_handler_key)

    attr_value = getattr(obj, k)
    yield inspect.unwrap(attr_value, stop=has_handler_key)


def _get_instance_member_candidates(v):
    yield inspect.unwrap(v, stop=has_handler_key)

    if inspect.ismethod(v):
        yield inspect.unwrap(v.__func__, stop=has_handler_key)


def has_handler_key(v):
    return hasattr(inspect.unwrap(v), '_handler_key')


def get_handler_key(v):
    return getattr(inspect.unwrap(v), '_handler_key')
