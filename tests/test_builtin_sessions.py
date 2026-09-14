import pytest
from scripts.builtin_session_client import BuiltinSessions,session_identifier

def test_session_identity_is_stable_and_owner_scoped():
    assert session_identifier('alice','chat')==session_identifier('alice','chat')
    assert session_identifier('alice','chat')!=session_identifier('bob','chat')
    assert session_identifier('alice','chat')!=session_identifier('alice','other')
    with pytest.raises(ValueError):session_identifier('','chat')

@pytest.mark.parametrize('endpoint',['http://eastus2.dynamicsessions.io/x','https://evil.example/x','https://eastus2.dynamicsessions.io.evil.example/x','https://eastus2.dynamicsessions.io/x','https://:secret@eastus2.dynamicsessions.io/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/test/sessionPools/test'])
def test_pool_client_rejects_unexpected_credential_destination(endpoint):
    with pytest.raises(ValueError):BuiltinSessions(endpoint,'not-a-real-token')
