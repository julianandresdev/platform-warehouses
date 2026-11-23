from common.errors import MessageError, PermanentError, TransientError


def test_jerarquia():
    assert issubclass(TransientError, MessageError)
    assert issubclass(PermanentError, MessageError)
    assert not issubclass(TransientError, PermanentError)
