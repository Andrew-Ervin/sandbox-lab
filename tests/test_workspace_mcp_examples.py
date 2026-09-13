"""Credential-free PR planning tests; SDK policy assertions run in its venv."""
import importlib.util
from pathlib import Path
import pytest

EXAMPLES=Path(__file__).resolve().parents[1]/'infra/azure-sandbox-pilot/examples'
spec=importlib.util.spec_from_file_location('pr_example',EXAMPLES/'github_pr.py')
pr=importlib.util.module_from_spec(spec);spec.loader.exec_module(pr)


def test_pr_plan_is_a_draft_and_does_not_push_or_merge():
    url,body=pr.request_plan('example','repo',title='Review changes',head='feature')
    assert url=='https://api.github.com/repos/example/repo/pulls'
    assert body=={'title':'Review changes','head':'feature','base':'main','draft':True}


def test_review_plan_targets_one_existing_pr():
    url,body=pr.request_plan('example','repo',review_number=12,reviewers=['reviewer'])
    assert url.endswith('/pulls/12/requested_reviewers')
    assert body=={'reviewers':['reviewer']}


@pytest.mark.parametrize('owner',['../outside','example/repo','example?x=1','*','a%2fb'])
def test_repo_path_injection_is_rejected(owner):
    with pytest.raises(ValueError):pr.request_plan(owner,'repo',title='Review',head='feature')
