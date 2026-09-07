"""Translate provider citations into ChatKit's native source annotations."""
from urllib.parse import urlsplit
from chatkit.types import Annotation, URLSource


def source_annotations(text, annotations):
    if not isinstance(annotations, list):
        return []
    sources=[];seen=set()
    for annotation in annotations[:64]:
        if not isinstance(annotation, dict) or annotation.get('type') != 'url_citation':
            continue
        citation=annotation.get('url_citation')
        if not isinstance(citation, dict):
            continue
        url=citation.get('url')
        if not isinstance(url, str) or len(url)>4096 or any(c.isspace() or ord(c)<32 for c in url):
            continue
        try:
            parsed=urlsplit(url)
            if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
                continue
        except ValueError:
            continue
        index=citation.get('end_index')
        if type(index) is not int or not 0<=index<=len(text):
            index=None
        if (url,index) in seen:
            continue
        seen.add((url,index))
        title=citation.get('title')
        description=citation.get('content')
        sources.append(Annotation(index=index,source=URLSource(
            url=url,title=title[:300] if isinstance(title,str) and title.strip() else parsed.hostname,
            description=description[:1000] if isinstance(description,str) else None)))
    return sources
