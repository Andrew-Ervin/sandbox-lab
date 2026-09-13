"""Review-only SDK policy examples. Prints JSON; never contacts Azure.

Run with the isolated Sandbox SDK Python. Production keeps its broker-mediated
package age checks; allowing PyPI directly would bypass that application gate.
"""
from dataclasses import asdict
import json
from azure.containerapps.sandbox import (
    EgressPolicy, EgressRule, EgressRuleMatch, EgressRuleAction,
    EgressHeader, EgressHeaderValueRef, EgressManagedIdentityRef,
)


def read_only_sources():
    # HTTPS Git clone also uses POST for upload-pack negotiation. This example
    # deliberately permits HTTP GET/HEAD only, not arbitrary Git operations.
    return EgressPolicy(default_action='Deny', traffic_inspection='Full', rules=[
        EgressRule(name='read-'+host.split('.')[0],
                   match=EgressRuleMatch(host=host, methods=['GET', 'HEAD']),
                   action=EgressRuleAction(type='Allow'))
        for host in ['github.com', 'api.github.com', 'raw.githubusercontent.com',
                     'dev.azure.com', 'pypi.org', 'files.pythonhosted.org']
    ])


def authenticated_api(host, audience):
    # Replace placeholders during operator review, not with workspace input.
    # The identity belongs to the group; target API authorization must still
    # constrain its application role to the intended operation/data scope.
    return EgressPolicy(default_action='Deny', traffic_inspection='Full', rules=[
        EgressRule(name='read-api', match=EgressRuleMatch(host=host, methods=['GET', 'HEAD']),
                   action=EgressRuleAction(type='Transform', headers=[
                       EgressHeader(name='Authorization', value_ref=EgressHeaderValueRef(
                           managed_identity_ref=EgressManagedIdentityRef(
                               resource=audience, format='Bearer {value}')))
                   ]))
    ])


if __name__ == '__main__':
    print(json.dumps({'read_only_sources':asdict(read_only_sources()),
                      'authenticated_api':asdict(authenticated_api('api.example.com', 'api://example-api'))}, indent=2))
