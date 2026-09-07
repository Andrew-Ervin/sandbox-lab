"""Render untrusted code/output without letting its own fences break a card."""
import re

def fenced(text, language='text'):
    fence='`'*max(3,1+max((len(m[0]) for m in re.finditer(r'`+',text)),default=0))
    return f'{fence}{language}\n{text}\n{fence}'
