import pytest
from scripts.builtin_session_client import BuiltinSessions,session_identifier

def test_session_identity_is_stable_and_owner_scoped():
    assert session_identifier('alice','chat')==session_identifier('alice','chat')
    assert session_identifier('alice','chat')!=session_identifier('bob','chat')
    assert session_identifier('alice','chat')!=session_identifier('alice','other')
    with pytest.raises(ValueError):session_identifier('','chat')

@pytest.mark.parametrize('endpoint',['http://eastus2.dynamicsessions.io/x','https://evil.example/x','https://eastus2.dynamicsessions.io.evil.example/x','https://eastus2.dynamicsessions.io/x'])
def test_pool_client_rejects_unexpected_credential_destination(endpoint):
    with pytest.raises(ValueError):BuiltinSessions(endpoint,'not-a-real-token')
