"""A self-contained image viewer served only on the isolated artifact origin."""
import base64,html

def render(raw,name,media):
    source='data:'+media+';base64,'+base64.b64encode(raw).decode()
    title=html.escape(name,quote=True)
    return ('''<!doctype html><html data-lab-viewer="image"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+title+'''</title><style>
*{box-sizing:border-box}body{margin:0;background:#171919;color:#e8eeeb;font:14px system-ui}header{height:48px;display:flex;gap:8px;align-items:center;padding:8px 12px;border-bottom:1px solid #353a37}header span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}button,a{color:inherit;background:#292e2b;border:1px solid #454d48;border-radius:6px;padding:5px 9px;text-decoration:none;cursor:pointer}button[aria-pressed=true]{background:#c1e8d0;color:#14251b}.stage{height:calc(100dvh - 48px);overflow:auto;display:grid;place-items:center;padding:16px}.stage.fit{display:block}.stage.fit img{display:block;margin:0 auto;max-width:100%;max-height:none;width:auto;height:auto;object-fit:contain}.stage.actual{display:block}.stage.actual img{max-width:none;max-height:none;display:block}img{border-radius:4px}
</style></head><body><header><span>'''+title+'''</span><button data-zoom="fit" aria-pressed="true">Fit width</button><button data-zoom="1" aria-pressed="false">100%</button><button data-zoom="2" aria-pressed="false">200%</button><a download="'''+title+'" href="'+source+'''" aria-label="Download image">↓</a></header><main class="stage fit"><img alt="'''+title+'" src="'+source+'''"></main><script>
const stage=document.querySelector('.stage'),img=document.querySelector('img');document.querySelectorAll('button').forEach(b=>b.onclick=()=>{const fit=b.dataset.zoom==='fit';stage.className='stage '+(fit?'fit':'actual');img.style.width=fit?'':img.naturalWidth*Number(b.dataset.zoom)+'px';document.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));stage.scrollTo(0,0);});
</script></body></html>''').encode()
