"""Keep the reviewed Pi webview assets inside its nonce-protected document.

The workspace preview deliberately cannot fetch vscode-cdn resource origins.
Embedding these fixed, packaged files avoids an external resource dependency.
"""
from pathlib import Path
import re


def patch(source: str) -> str:
    if 'LAB_INLINE_WEBVIEW' in source:
        return source
    fs = re.search(r'([\w$]+)=(?:[\w$]+\()?require\("fs"\)', source)
    path = re.search(r'([\w$]+)=(?:[\w$]+\()?require\("path"\)', source)
    if not fs or not path:
        raise RuntimeError('Unexpected Pi extension imports')

    def asset(name: str, tag: str) -> str:
        # These are fixed package paths, never message or workspace content.
        return '${' + fs[1] + '.readFileSync(' + path[1] + '.join(this.extensionUri.fsPath,"media","' + name + '"),"utf8").replace(/<\\/' + tag + '/gi,"<\\\\/' + tag + '")}'

    substitutions = {
        '<link rel="stylesheet" href="${t}">': '<!-- LAB_INLINE_WEBVIEW --><style>' + asset('style.css', 'style') + '</style>',
        '<script nonce="${s}" src="${r}"></script>': '<script nonce="${s}">' + asset('vendor.js', 'script') + '</script>',
        '<script nonce="${s}" src="${n}"></script>': '<script nonce="${s}">' + asset('main.js', 'script') + '</script>',
    }
    for old, new in substitutions.items():
        if source.count(old) != 1:
            raise RuntimeError('Unexpected Pi webview asset markup')
        source = source.replace(old, new, 1)
    return source


if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'sandbox/pi-chat/out/extension.js'
    target.write_text(patch(target.read_text()))
