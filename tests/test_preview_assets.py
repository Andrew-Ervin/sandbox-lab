from backend.preview_assets import rewrite


def test_vite_html_and_transitive_imports_keep_capability():
    assert b'src="/_lab/token/@vite/client"' in rewrite(b'<script src="/@vite/client"></script>', 'text/html', 'token')
    result=rewrite(b'import x from "/node_modules/.vite/deps/react.js"; const base = "/";', 'application/javascript', 'token')
    assert b'"/_lab/token/node_modules/' in result
    assert b'base = "/_lab/token/"' in result


def test_external_urls_and_existing_scopes_are_unchanged():
    body=b'"//external.test/a" "https://external.test/b" "/_lab/token/x"'
    assert rewrite(body,'text/javascript','token')==body
    assert rewrite(b'"/binary"','application/octet-stream','token')==b'"/binary"'


def test_css_unquoted_root_assets_are_scoped():
    assert rewrite(b'url(/font.woff2)','text/css','token')==b'url(/_lab/token/font.woff2)'


def test_javascript_slash_separator_is_not_a_url():
    assert rewrite(b'value.split("/")','application/javascript','token')==b'value.split("/")'
