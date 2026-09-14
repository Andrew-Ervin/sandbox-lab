"""Embed bounded public README raster images; never proxy arbitrary URLs."""
import base64
import io
import re
from urllib.parse import urlsplit
import httpx
from PIL import Image


def allowed(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.query or p.fragment or any(x in p.path for x in ('..','\\','%')):return False
    if not re.search(r'\.(png|jpe?g|gif|webp)$',p.path,re.I):return False
    if p.netloc=='github.com':return bool(re.fullmatch(r'/[\w.-]+/[\w.-]+/raw/.+',p.path))
    return p.netloc=='raw.githubusercontent.com' and bool(re.fullmatch(r'/[\w.-]+/[\w.-]+/.+',p.path))


async def embed(content,client):
    text=content.decode('utf-8',errors='replace')
    # Only image references, not ordinary links or arbitrary document URLs.
    urls=list(dict.fromkeys(re.findall(r'!\[[^\]\n]*\]\((https://[^\s)]+)',text)+re.findall(r'<img\b[^>]*\bsrc=["\'](https://[^"\']+)',text,re.I)))[:8]
    total=0
    for original in urls:
        if not allowed(original):continue
        try:
            url=original
            for _ in range(3):
                if not allowed(url):break
                async with client.stream('GET',url,timeout=5) as response:
                    if response.status_code in (301,302,303,307,308):url=response.headers.get('location','');continue
                    if response.status_code!=200:break
                    data=bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data)+len(chunk)>2_000_000:raise ValueError('Image too large')
                        data.extend(chunk)
                    with Image.open(io.BytesIO(data)) as image:
                        if image.width*image.height>8_000_000:raise ValueError('Image dimensions too large')
                        image.thumbnail((1920,1920))
                        output=io.BytesIO();image.convert('RGB' if image.mode=='RGB' else 'RGBA').save(output,format='PNG')
                    image_bytes=output.getvalue()
                    if len(image_bytes)>4_000_000 or total+len(image_bytes)>8_000_000:break
                    total+=len(image_bytes)
                    text=text.replace(original,'data:image/png;base64,'+base64.b64encode(image_bytes).decode())
                    break
        except (httpx.HTTPError,ValueError,OSError,Image.DecompressionBombError):continue
    return text.encode()
