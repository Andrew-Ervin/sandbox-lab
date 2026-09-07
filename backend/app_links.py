"""Keep known internal app and artifact links in the authenticated in-app preview flow."""
import re
from urllib.parse import unquote

APP_LINK=re.compile(r'(?<=\()(?:https?://(?:127\.0\.0\.1|localhost):3000)?/api/app-preview/(run_[a-f0-9]{32})(?=\))')

FILE_LINK=re.compile(r'(?<=\()(?:https?://(?:127\.0\.0\.1|localhost):3000)?/api/artifact-view/(run_[a-f0-9]{32})/([^\)\n]+)(?=\))')

def app_links(text):
    def file_link(match):
        name=unquote(match[2])
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_. -]{0,159}',name) or '..' in name:return match[0]
        return 'chatkit-link://file-'+match[1]+'-'+name.encode().hex()
    text=FILE_LINK.sub(file_link,text)
    return APP_LINK.sub(lambda match:'chatkit-link://app-'+match[1],text)
