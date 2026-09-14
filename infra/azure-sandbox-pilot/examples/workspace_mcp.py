"""Operator-reviewed MCP/PR egress examples; no Azure calls or credentials.

Run with the isolated Sandbox SDK Python. JSON uses the SDK wire serializer.
An allowlisted MCP endpoint is not a tool authorization policy: enforce read-only
upstream, and use a separate, narrowly scoped credential for write operations.
"""
import argparse
import json
import re
from azure.containerapps.sandbox import (
    EgressPolicy, EgressRule, EgressRuleMatch, EgressRuleAction,
    EgressHeader, EgressHeaderValueRef, EgressSecretRef,
)


def segment(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value) or '..' in value:
        raise ValueError('Expected one literal resource-name segment')
    return value


def rule(name, host, path, methods, headers=None):
    return EgressRule(name=name, match=EgressRuleMatch(host=host, path=path, methods=methods),
                      action=EgressRuleAction(type='Transform' if headers else 'Allow', headers=headers))


def bearer(secret):
    return EgressHeader(name='Authorization', value_ref=EgressHeaderValueRef(
        secret_ref=EgressSecretRef(secret_id=segment(secret), format='Bearer {value}')))


def github_pr(owner, repo, secret=None, review_number=None):
    """One repository: create a PR, optionally request review on one known PR.

    No PATCH/PUT/DELETE, merge, branch push, or arbitrary /repos/* permission.
    Credentials must independently restrict the repository and PR permission.
    """
    base=f'/repos/{segment(owner)}/{segment(repo)}'
    headers=[bearer(secret)] if secret else None
    rules=[rule('read-repository', 'api.github.com', base, ['GET'], headers),
           rule('create-pull-request', 'api.github.com', base+'/pulls', ['POST'], headers)]
    if review_number is not None:
        if type(review_number) is not int or review_number < 1:
            raise ValueError('Expected a positive PR number')
        path=base+'/pulls/'+str(review_number)
        rules.extend([rule('read-pull-request','api.github.com',path,['GET'],headers),
                      rule('request-review','api.github.com',path+'/requested_reviewers',['POST'],headers)])
    return EgressPolicy(default_action='Deny',traffic_inspection='Full',rules=rules)


def remote_mcp(github_secret=None):
    """Microsoft Learn needs no credential. Optional GitHub is read-only.
    No login endpoints or direct Git/API/package hosts are opened here.
    """
    common=[EgressHeader(name='X-MCP-Readonly', value='true')]
    rules=[rule('microsoft-learn','learn.microsoft.com','/api/mcp',['GET','POST','DELETE'])]
    if github_secret:rules.append(
        rule('github-mcp','api.githubcopilot.com','/mcp/', ['GET','POST','DELETE'],
             [bearer(github_secret), *common, EgressHeader(name='X-MCP-Toolsets',value='repos,pull_requests')]))
    return EgressPolicy(default_action='Deny', traffic_inspection='Full', rules=rules)


def native_create(connection_ids):
    pattern=r'/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9_.()-]+/providers/Microsoft.Web/connectorGateways/[A-Za-z0-9_-]+/mcpserverconfigs/[A-Za-z0-9_-]+'
    if not 1<=len(connection_ids)<=10 or len(set(connection_ids))!=len(connection_ids):
        raise ValueError('Provide 1-10 distinct MCP connector IDs')
    if any(not re.fullmatch(pattern, ident) for ident in connection_ids):
        raise ValueError('Expected a Connector Namespace MCP resource ID')
    return {'disk':'claude','cpu':'1000m','memory':'2048Mi',
            'auto_suspend_seconds':600,'auto_suspend_mode':'Memory',
            'connections':connection_ids}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['native','remote','pr'],required=True)
    parser.add_argument('--connection-id',action='append',default=[])
    parser.add_argument('--owner',default='example-owner')
    parser.add_argument('--repo',default='example-repo')
    parser.add_argument('--github-secret')
    parser.add_argument('--review-number',type=int)
    args=parser.parse_args()
    if args.mode=='native':result=native_create(args.connection_id)
    elif args.mode=='remote':result=remote_mcp(args.github_secret)._to_dict()
    else:result=github_pr(args.owner,args.repo,args.github_secret,args.review_number)._to_dict()
    print(json.dumps(result,indent=2))
