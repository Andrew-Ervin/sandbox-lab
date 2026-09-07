"""Read-only request preview. No HTML, URL, or attachment can execute or fetch."""
import base64
import binascii
import html
import json
from html.parser import HTMLParser

MAX_PAYLOAD = 1_000_000
ALLOWED_TAGS = frozenset('p br div span strong b em i u s h1 h2 h3 h4 ul ol li blockquote pre code table thead tbody tfoot tr th td hr a img'.split())
VOID_TAGS = {'br', 'hr', 'img'}
HIDDEN_TAGS = {'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math', 'form', 'template', 'noscript'}


def raster_data(value):
    """Only embedded raster images; never fetch remote images or parse SVG."""
    if not isinstance(value, str) or len(value) > 700_000:
        return None
    prefix, separator, encoded = value.partition(',')
    types = {'data:image/png;base64': b'\x89PNG\r\n\x1a\n',
             'data:image/jpeg;base64': b'\xff\xd8\xff',
             'data:image/gif;base64': b'GIF8', 'data:image/webp;base64': b'RIFF'}
    if not separator or prefix not in types:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return None
    if not raw.startswith(types[prefix]) or len(raw) > 512_000:
        return None
    if prefix == 'data:image/webp;base64' and raw[8:12] != b'WEBP':
        return None
    return prefix + ',' + base64.b64encode(raw).decode()


class SafeEmailHTML(HTMLParser):
    def __init__(self, images):
        super().__init__(convert_charrefs=True)
        self.images = images
        self.parts = []
        self.stack = []
        self.hidden = []
        self.blocked_images = 0

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            if tag in HIDDEN_TAGS:
                self.hidden.append(tag)
            return
        if tag in HIDDEN_TAGS:
            self.hidden.append(tag)
            return
        if tag not in ALLOWED_TAGS:
            return
        attrs = dict(attrs)
        if tag == 'img':
            src = attrs.get('src') or ''
            source = self.images.get(src[4:].strip('<>')) if src.startswith('cid:') else raster_data(src)
            if source:
                self.parts.append('<img src="' + html.escape(source, quote=True) + '" alt="' + html.escape(attrs.get('alt') or 'Inline image', quote=True) + '">')
            else:
                self.blocked_images += 1
                self.parts.append('<span class="blocked-image">Image not loaded' + (' · ' + html.escape(attrs['alt']) if attrs.get('alt') else '') + '</span>')
            return
        # No attributes from the payload survive: no handlers, links, CSS, classes,
        # IDs, form actions, media sources, or resource-loading URLs.
        rendered = 'span' if tag == 'a' else tag
        self.parts.append('<' + rendered + '>')
        if tag not in VOID_TAGS:
            self.stack.append((tag, rendered))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        found = next((i for i in range(len(self.stack)-1, -1, -1) if self.stack[i][0] == tag), None)
        if found is not None:
            while len(self.stack) > found:
                self.parts.append('</' + self.stack.pop()[1] + '>')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(html.escape(data))

    def result(self):
        self.close()
        while self.stack:
            self.parts.append('</' + self.stack.pop()[1] + '>')
        return ''.join(self.parts)


def recipients(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ', '.join(filter(None, (recipients(item) for item in value)))
    if isinstance(value, dict):
        address = value.get('emailAddress', value)
        if isinstance(address, dict):
            name, email = address.get('name', ''), address.get('address', '')
            if isinstance(name, str) and isinstance(email, str):
                return f'{name} <{email}>' if name else email
    return ''


def formatted(payload):
    message = payload.get('message', payload) if isinstance(payload, dict) else {}
    if not isinstance(message, dict) or not ('body' in message or 'html' in message):
        return '<div class="empty">This request has no email body. Use JSON to inspect the complete operation.</div>'
    images = {}
    attachments = message.get('attachments', [])
    for attachment in attachments[:20] if isinstance(attachments, list) else []:
        if not isinstance(attachment, dict) or attachment.get('isInline') is not True:
            continue
        cid, mime, encoded = (attachment.get(k) for k in ('contentId', 'contentType', 'contentBytes'))
        if all(isinstance(v, str) for v in (cid, mime, encoded)):
            data = raster_data('data:' + mime + ';base64,' + encoded)
            if data:
                images[cid.strip('<>')] = data
    body = message.get('body', '')
    is_html = False
    if isinstance(body, dict):
        is_html = str(body.get('contentType', '')).lower() == 'html'
        body = body.get('content', '')
    elif isinstance(message.get('html'), str):
        body, is_html = message['html'], True
    if not isinstance(body, str):
        body = ''
    if is_html:
        sanitizer = SafeEmailHTML(images)
        sanitizer.feed(body)
        content = sanitizer.result()
    else:
        content = '<div class="plain-body">' + html.escape(body) + '</div>'
    fields = []
    for label, keys in [('To', ('to', 'toRecipients')), ('Cc', ('cc', 'ccRecipients')), ('Bcc', ('bcc', 'bccRecipients'))]:
        value = recipients(next((message[k] for k in keys if k in message), ''))
        if value:
            fields.append('<div><dt>' + label + '</dt><dd>' + html.escape(value) + '</dd></div>')
    subject = message.get('subject', 'Untitled message')
    subject = subject if isinstance(subject, str) else 'Untitled message'
    return ('<article class="email"><header><p class="eyebrow">Email preview</p><h1>' + html.escape(subject) + '</h1><dl>' + ''.join(fields) +
            '</dl></header><div class="email-body">' + content + '</div></article>' +
            '<p class="note">Safe content preview. Text structure and embedded raster images are shown; active content, external images, links, and custom styles are disabled. Email-client rendering may differ.</p>')


def render(raw, name='Request details'):
    if len(raw) > MAX_PAYLOAD:
        raise ValueError('Request is too large to preview')
    text = raw.decode('utf-8')
    try:
        payload = json.loads(text)
        formatted_html = formatted(payload)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    except (ValueError, RecursionError):
        formatted_html = '<div class="empty">A formatted preview is unavailable. The original request is available in JSON.</div>'
    # CSS-only controls need no executable code from the request, even for tabs.
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(name) + '</title><style>' + STYLE + '</style></head><body>'
            '<main class="review"><input class="tab-radio" type="radio" name="view" id="formatted" checked aria-label="Formatted preview"><input class="tab-radio" type="radio" name="view" id="json" aria-label="JSON">'
            '<nav aria-label="Request views"><strong>Request details</strong><div class="tabs"><label for="formatted">Preview</label><label for="json">JSON</label></div></nav>'
            '<section class="formatted-pane" aria-label="Formatted request">' + formatted_html + '</section>'
            '<section class="json-pane" aria-label="Exact JSON payload"><p class="note">Complete request payload. Viewing does not approve or send it.</p><pre class="source"><code>' + html.escape(text) + '</code></pre></section></main></body></html>').encode()


STYLE = '''*{box-sizing:border-box}html{color-scheme:dark}body{margin:0;background:#202220;color:#dce4de;font:14px/1.6 system-ui,sans-serif}nav{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 20px;background:#282c29;border-bottom:1px solid #ffffff16}nav strong{font-size:13px;font-weight:550}.tabs{display:flex;gap:3px;background:#191c1a;padding:3px;border-radius:8px}.tabs label{padding:5px 16px;border-radius:6px;cursor:pointer;color:#a8b3ab;font-size:12px}.tab-radio{position:absolute;opacity:0;width:1px;height:1px}#formatted:checked~nav label[for=formatted],#json:checked~nav label[for=json]{background:#3a453d;color:#ecf6ef}#formatted:focus-visible~nav label[for=formatted],#json:focus-visible~nav label[for=json]{outline:2px solid #b4e4cc;outline-offset:2px}.formatted-pane,.json-pane{padding:24px;max-width:1000px;margin:auto}.json-pane{display:none}#json:checked~.formatted-pane{display:none}#json:checked~.json-pane{display:block}.email{background:#fff;color:#222b25;border-radius:12px;overflow:hidden;border:1px solid #e7eae8;box-shadow:0 8px 30px #0002}.email header{padding:26px 30px 22px;border-bottom:1px solid #e6e9e7}.eyebrow{text-transform:uppercase;letter-spacing:.11em;font-size:10px;color:#68796d;margin:0 0 9px}h1{font-size:22px;line-height:1.35;letter-spacing:-.025em;margin:0 0 18px;font-weight:600;overflow-wrap:anywhere}dl{margin:0;font-size:12px}dl>div{display:flex;gap:12px;margin-top:5px}dt{color:#7d8981;min-width:25px}dd{margin:0;overflow-wrap:anywhere}.email-body{padding:26px 30px;font:14px/1.75 Arial,sans-serif;overflow-wrap:anywhere}.plain-body{white-space:pre-wrap}.email-body p{margin:0 0 1.15em}.email-body img{display:block;max-width:100%;height:auto;margin:16px 0;border-radius:6px}.email-body table{border-collapse:collapse;max-width:100%;display:block;overflow:auto}.email-body td,.email-body th{padding:8px;border:1px solid #dae0db}.email-body blockquote{margin:16px 0;padding:0 16px;border-left:3px solid #d6dfd8}.email-body pre{white-space:pre-wrap;overflow-wrap:anywhere}.blocked-image{display:block;padding:16px;margin:12px 0;border:1px dashed #b8c4bc;background:#f2f5f3;border-radius:6px;color:#6e7c73;font-size:12px}.note,.empty{color:#9daf9f;font-size:12px;line-height:1.65}.note{margin:16px 0}.source{background:#181c19;border:1px solid #ffffff14;border-radius:10px;padding:20px;overflow:auto;font:12px/1.85 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}html[data-lab-fit="false"] .source{white-space:pre;overflow-wrap:normal}@media(max-width:500px){.formatted-pane,.json-pane{padding:14px}.email header,.email-body{padding:20px}h1{font-size:19px}}'''
