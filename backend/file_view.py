"""Bounded, escaped previews for data and source files on the isolated origin."""
import codecs,csv,html,io,json
from pathlib import Path

def render(raw,name):
    e=html.escape;shown=raw[:200_000];truncated=len(raw)>len(shown);suffix=Path(name).suffix.lower()
    try:
        text=codecs.getincrementaldecoder('utf-8-sig')().decode(shown,final=not truncated)
        if '\0' in text:raise UnicodeError()
    except UnicodeError:
        body='<div class="empty">A preview is not available for this binary file. Use Download on its chat card or in Conversation files.</div>';label='Binary file'
    else:
        label='JSON payload' if suffix=='.json' else 'Source preview';body=''
        if suffix in ('.csv','.tsv'):
            try:
                rows=[]
                for i,row in enumerate(csv.reader(io.StringIO(text),delimiter='\t' if suffix=='.tsv' else ',')):
                    if i>=501:truncated=True;break
                    if len(row)>40:truncated=True
                    rows.append(row[:40])
                if rows:
                    label=f'Table · {max(0,len(rows)-1)} rows shown'
                    body='<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+e(c)+'</th>' for c in rows[0])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(c)+'</td>' for c in row)+'</tr>' for row in rows[1:])+'</tbody></table></div>'
            except csv.Error:pass
        if not body:
            if suffix=='.json' and not truncated:
                try:text=json.dumps(json.loads(text),ensure_ascii=False,indent=2)
                except (ValueError,RecursionError):pass
            lines=text[:200_000].splitlines();truncated=truncated or len(text)>200_000 or len(lines)>3000
            body='<ol class="source">'+''.join('<li><code>'+e(line)+'</code></li>' for line in lines[:3000])+'</ol>'
    note='<p class="notice">Preview shortened. Download the original file for all content.</p>' if truncated else ''
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(name)+'</title><style>'+STYLE+'</style></head><body><header><strong>'+e(name)+'</strong><span>'+e(label)+'</span></header><main>'+body+note+'</main></body></html>').encode()

STYLE='''*{box-sizing:border-box}html{color-scheme:dark}body{margin:0;background:#202220;color:#dce4de;font:14px/1.6 system-ui,sans-serif}header{position:sticky;top:0;z-index:2;background:#282c29;border-bottom:1px solid #ffffff16;padding:16px 22px;display:flex;justify-content:space-between;align-items:center;gap:16px}header strong{font-size:13px;font-weight:550;overflow-wrap:anywhere}header span{font-size:11px;color:#a0b4a7;white-space:nowrap}main{padding:20px}.table-wrap{overflow:auto;max-height:calc(100vh - 115px);border:1px solid #ffffff16;border-radius:9px}table{border-collapse:separate;border-spacing:0;width:100%;font-variant-numeric:tabular-nums}th,td{padding:10px 16px;text-align:left;border-bottom:1px solid #ffffff0e;min-width:90px;white-space:pre-wrap;overflow-wrap:anywhere;max-width:500px}th{position:sticky;top:0;background:#2b342e;color:#bed7c6;font-weight:550;font-size:12px}tr:last-child td{border-bottom:0}tbody tr:nth-child(even){background:#ffffff03}tbody tr:hover{background:#ffffff07}.source{margin:0;padding:12px 14px 12px 4em;border:1px solid #ffffff13;border-radius:9px;background:#1a1d1b;overflow:auto;font:12px/1.85 ui-monospace,monospace}.source li{padding-left:13px;white-space:pre;min-height:1.85em}html[data-lab-fit="true"] .source li{white-space:pre-wrap;overflow-wrap:anywhere}.source li::marker{color:#64756a}.source code{font:inherit}.notice,.empty{font-size:13px;color:#9aaba0;padding:18px;line-height:1.7}.notice{border-top:1px solid #ffffff14;margin-top:20px}'''
