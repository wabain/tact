import uuid

import pytest
import voluptuous

from tact.networking.wire import (
    ServerMsgType,
    ClientMsgType,
    ServerMessage,
    ClientMessage,
)


NONCE = 'f4e720bf-fa19-470e-abb2-a309b49083ab'

SERVER_MSG = {
    'version': '0.1',
    'msg_id': 100,
    'msg': {
        'type': ServerMsgType.GAME_JOINED.value,
        'game_id': 'dummy-game-id',
        'player_nonce': NONCE,
    },
}


def test_server_message_build():
    msg = ServerMessage.build(
        ServerMsgType.GAME_JOINED,
        msg_id=100,
        game_id='dummy-game-id',
        player_nonce=NONCE,
    )
    assert msg == SERVER_MSG


def test_server_message_build_invalid_nonce():
    # TODO: refactor to get better error message
    with pytest.raises(voluptuous.MultipleInvalid):
        ServerMessage.build(
            ServerMsgType.GAME_JOINED,
            msg_id=100,
            game_id='dummy-game-id',
            player_nonce='100',
        )


def test_server_message_parse():
    msg_type, payload = ServerMessage.parse(SERVER_MSG)
    assert msg_type == ServerMsgType.GAME_JOINED
    assert payload == {
        'type': ServerMsgType.GAME_JOINED.value,
        'game_id': 'dummy-game-id',
        'player_nonce': uuid.UUID(NONCE),
    }


def test_server_message_parse_invalid_nonce():
    with pytest.raises(voluptuous.MultipleInvalid):
        ServerMessage.parse(dict(SERVER_MSG, msg=dict(SERVER_MSG['msg'], nonce='100')))


def test_server_message_parse_invalid_version():
    errs = None

    with pytest.raises(voluptuous.MultipleInvalid):
        try:
            ServerMessage.parse(dict(SERVER_MSG, version='3.5'))
        except voluptuous.MultipleInvalid as exc:
            errs = exc.errors
            raise

    assert [e.path for e in errs] == [['version']]
