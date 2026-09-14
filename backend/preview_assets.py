"""Keep root-relative app assets inside their opaque preview capability path."""
import re

# Covers HTML attributes, JS module/URL literals and CSS url(). Never rewrite
# protocol-relative external destinations or already-prefixed capability paths.
_LITERAL = re.compile(rb'''(["'`])(/(?!/|_lab/)[^"'`\s<>\\]*)\1''')
_CSS = re.compile(rb'''(url\(\s*)(/(?!/|_lab/)[^\s)'"<>\\]*)(\s*\))''')

def rewrite(body, content_type, capability):
    if not any(kind in content_type for kind in ('text/html','javascript','text/css')):
        return body
    prefix=b'/_lab/'+capability.encode()+b'/'
    def scoped(match):
        # A bare slash in JavaScript can be a separator, not a URL.
        if 'javascript' in content_type and match[2]==b'/':return match[0]
        return match[1]+prefix+match[2][1:]+match[1]
    body=_LITERAL.sub(scoped,bytes(body))
    if 'javascript' in content_type:
        # Vite emits these named base variables for module/HMR routing.
        body=re.sub(rb'''(\b(?:const|let|var)\s+(?:base|hmrBase)\s*=\s*)(["'])/\2''',lambda m:m[1]+m[2]+prefix+m[2],body)
    if 'text/css' in content_type:
        body=_CSS.sub(lambda m:m[1]+prefix+m[2][1:]+m[3],body)
    return bytearray(body)
