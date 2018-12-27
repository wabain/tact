"""Handle the client-server wire protocol

This module actually implements fairly high-level functionality; it handles
translated JSON payloads to and from an internal representation.
"""

from __future__ import annotations

import uuid
import enum
import typing as typ
from typing import Callable, Tuple

from voluptuous import Schema
from voluptuous.validators import Any, Coerce


#
# VALIDATION
#


def ProtocolVersion(v: typ.Any) -> str:
    if v != '0.1':
        raise ValueError(f'Unsupported protocol version {v} (expected 0.1)')
    return v


PlayerID = Any(1, 2)

# Shared messages

illegal_msg_schema = Schema(
    {'type': 'illegal_msg', 'error': str, 'err_msg_id': Any(int, None)}, required=True
)

# Client messages

new_game_schema = Schema(
    {'type': 'new_game', 'player': PlayerID, 'squares_per_row': int, 'run_to_win': int},
    required=True,
)

join_game_schema = Schema(
    {'type': 'join_game', 'game_id': str, 'player': PlayerID}, required=True
)

rejoin_game_schema = Schema(
    {
        'type': 'rejoin_game',
        'game_id': str,
        'player': PlayerID,
        'player_nonce': Coerce(uuid.UUID),
    },
    required=True,
)

client_msg_schema = Schema(
    {
        'version': ProtocolVersion,
        'msg_id': int,
        'msg': Any(
            illegal_msg_schema, new_game_schema, join_game_schema, rejoin_game_schema
        ),
    },
    required=True,
)

# Server messages

game_joined_schema = Schema(
    {
        'type': 'game_joined',
        'game_id': str,
        'player_nonce': lambda nonce: uuid.UUID(nonce),
    }
)

move_pending_schema = Schema(
    {'type': 'move_pending', 'player': PlayerID}, required=True
)

illegal_move_schema = Schema({'type': 'illegal_move', 'error': str}, required=True)

game_over_schema = Schema(
    {
        'type': 'game_over',
        'winner': Any(PlayerID, None),
        'is_draw': bool,
        'is_technical_forfeit': bool,
        'is_user_forfeit': bool,
    },
    required=True,
)

server_msg_schema = Schema(
    {
        'version': ProtocolVersion,
        'msg_id': int,
        'msg': Any(
            illegal_msg_schema,
            game_joined_schema,
            move_pending_schema,
            illegal_move_schema,
            game_over_schema,
        ),
    },
    required=True,
)


#
# SERIALIZATION/DESERIALIZATION
#


class ClientMsgType(enum.Enum):
    ILLEGAL_MSG = 'illegal_msg'
    NEW_GAME = 'new_game'
    JOIN_GAME = 'join_game'
    REJOIN_GAME = 'rejoin_game'


class ServerMsgType(enum.Enum):
    ILLEGAL_MSG = 'illegal_msg'
    GAME_JOINED = 'game_joined'
    MOVE_PENDING = 'move_pending'
    ILLEGAL_MOVE = 'illegal_move'
    GAME_OVER = 'game_over'


class ClientMessage:
    @staticmethod
    def parse(msg: typ.Any) -> Tuple[ClientMsgType, dict]:
        msg = client_msg_schema(msg)
        msg_type = ClientMsgType(msg['msg']['type'])
        return msg_type, msg['msg']

    @staticmethod
    def build(msg_type: ClientMsgType, msg_id: int, **kwargs) -> dict:
        payload = dict(type=msg_type.value, **kwargs)
        return _build_msg(msg_id=msg_id, payload=payload, validate=client_msg_schema)


class ServerMessage:
    @staticmethod
    def parse(msg: typ.Any) -> Tuple[ServerMsgType, dict]:
        msg = server_msg_schema(msg)
        msg_type = ServerMsgType(msg['msg']['type'])
        return msg_type, msg['msg']

    @staticmethod
    def build(msg_type: ServerMsgType, msg_id: int, **kwargs) -> dict:
        payload = dict(type=msg_type.value, **kwargs)
        return _build_msg(msg_id=msg_id, payload=payload, validate=server_msg_schema)


def _build_msg(
    *, msg_id: int, payload: typ.Any, validate: Callable[[typ.Any], dict]
) -> dict:
    msg = {'version': '0.1', 'msg_id': msg_id, 'msg': payload}
    validate(msg)
    return msg
