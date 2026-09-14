"""Run INSIDE a sandbox with the reviewed PR egress policy and injected auth.

No PAT environment variable is required. Plans by default; --submit performs
exactly one write. It never retries a timed-out write or merges a pull request.
"""
import argparse
import json
import re
import urllib.error
import urllib.request


def request_plan(owner, repo, *, title=None, head=None, base='main', review_number=None, reviewers=()):
    for part in (owner,repo):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',part) or '..' in part:
            raise ValueError('Invalid repository')
    url=f'https://api.github.com/repos/{owner}/{repo}/pulls'
    if review_number is not None:
        if type(review_number) is not int or review_number<1 or not reviewers:
            raise ValueError('Specify a PR number and reviewer usernames')
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',r) for r in reviewers):
            raise ValueError('Invalid reviewer')
        return url+f'/{review_number}/requested_reviewers',{'reviewers':list(reviewers)}
    if not title or not head or not base or max(map(len,(title,head,base)))>256:
        raise ValueError('Specify a title, existing head branch, and base branch')
    return url,{'title':title,'head':head,'base':base,'draft':True}


def submit(url, body):
    # Do not forward a request to another host or replay its body on redirect.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    request=urllib.request.Request(url,data=json.dumps(body).encode(),method='POST',headers={
        'Accept':'application/vnd.github+json','Content-Type':'application/json',
        'User-Agent':'sandbox-lab-pr-example','X-GitHub-Api-Version':'2022-11-28'})
    with opener.open(request,timeout=30) as response:
        payload=json.loads(response.read(1_000_000))
        return {k:payload[k] for k in ('number','html_url','state','draft') if k in payload}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner',required=True);parser.add_argument('--repo',required=True)
    parser.add_argument('--title');parser.add_argument('--head');parser.add_argument('--base',default='main')
    parser.add_argument('--review-number',type=int);parser.add_argument('--reviewer',action='append',default=[])
    parser.add_argument('--submit',action='store_true')
    args=parser.parse_args()
    url,body=request_plan(args.owner,args.repo,title=args.title,head=args.head,base=args.base,
                          review_number=args.review_number,reviewers=args.reviewer)
    if not args.submit:print(json.dumps({'method':'POST','url':url,'body':body,'submitted':False},indent=2))
    else:
        try:print(json.dumps({'submitted':True,'result':submit(url,body)}))
        except Exception as error:
            # A lost response can follow a successful write. Reconcile on GitHub.
            raise SystemExit(f'Request outcome needs verification on GitHub ({type(error).__name__}); do not blindly retry.') from None
