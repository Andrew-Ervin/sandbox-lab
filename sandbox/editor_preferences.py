"""Portable user preferences only; no credentials, chats or workspace state."""
import json
import re
import sqlite3
import os
import tempfile
from pathlib import Path

USER=Path.home()/'.local/share/code-server/User'
WORKSPACE=Path.home()/'project/.vscode/settings.json'
APPEARANCE={'workbench.colorTheme','workbench.iconTheme','workbench.preferredDarkColorTheme','workbench.preferredLightColorTheme','editor.fontSize','editor.fontFamily','window.zoomLevel'}
PREFIXES=('editor.','workbench.color','workbench.icon','workbench.preferred','workbench.editor.','workbench.sideBar.','workbench.panel.','workbench.activityBar.','workbench.startupEditor','window.zoomLevel','files.autoSave','explorer.','terminal.integrated.font')
LAYOUT_KEYS={'workbench.activity.pinnedViewlets2','workbench.activity.placeholderViewlets','workbench.panel.pinnedPanels','workbench.panel.placeholderPanels','workbench.auxiliarybar.pinnedPanels','workbench.auxiliarybar.placeholderPanels','workbench.sidebar.location','workbench.sidebar.activeviewletid','workbench.auxiliarybar.activepanelid','workbench.panel.location','workbench.sidebar.width','workbench.panel.size','workbench.auxiliarybar.width'}

def parse_jsonc(text):
    # Editor preference files permit comments and trailing commas. Preserve
    # quoted strings (including URLs) while removing only JSONC syntax.
    tokens=re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/',re.S)
    plain=tokens.sub(lambda m:m.group(0) if m.group(0).startswith('"') else ' ',text)
    trailing=re.compile(r'"(?:\\.|[^"\\])*"|,(\s*[}\]])',re.S)
    return json.loads(trailing.sub(lambda m:m.group(0) if m.group(1) is None else m.group(1),plain))


def read(path,default):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>512000:return default
    try:return parse_jsonc(path.read_text())
    except ValueError:return default

def settings(value):
    if not isinstance(value,dict):raise ValueError('Invalid preferences')
    return {k:v for k,v in value.items() if isinstance(k,str) and k.startswith(PREFIXES) and len(json.dumps(v))<=16000}

def export():
    state={};db=USER/'globalStorage/state.vscdb'
    if db.is_file() and not db.is_symlink():
        with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as connection:
            state={k:v for k,v in connection.execute('SELECT key,value FROM ItemTable') if k in LAYOUT_KEYS and len(v)<=16000}
    bindings=read(USER/'keybindings.json',[])
    extensions=read(USER.parent/'extensions/extensions.json',[])
    portable=settings(read(USER/'settings.json',{}))
    workspace=read(WORKSPACE,{})
    portable.update({k:v for k,v in (workspace.items() if isinstance(workspace,dict) else []) if k in APPEARANCE})
    return {'settings':portable, 'keybindings':bindings if isinstance(bindings,list) and len(bindings)<=250 else [],
        'extensions':sorted({e.get('identifier',{}).get('id','').lower() for e in extensions if re.fullmatch(r'[\w-]+\.[\w-]+',e.get('identifier',{}).get('id',''))}), 'layout':state}

def atomic_write(path, data):
    fd, name = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def apply(value):
    USER.mkdir(parents=True,exist_ok=True)
    path=USER/'settings.json'
    if path.is_symlink():raise ValueError('Unsafe settings path')
    original=read(path,{})
    for key in list(original):
        if key.startswith(PREFIXES):original.pop(key)
    original.update(settings(value.get('settings',{})))
    atomic_write(path,json.dumps(original,indent=2).encode())
    # Earlier agents wrote account appearance into project settings. Back up
    # those overrides and let the shared user profile take effect on reopen.
    overrides=read(WORKSPACE,{})
    if not isinstance(overrides,dict):overrides={}
    if any(k in APPEARANCE for k in overrides) and not WORKSPACE.is_symlink():
        backup=WORKSPACE.with_suffix('.json.before-account-profile')
        try:
            fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            if backup.is_symlink():raise ValueError('Unsafe preference backup')
        else:
            with os.fdopen(fd,'wb') as output:output.write(WORKSPACE.read_bytes())
        remaining={k:v for k,v in overrides.items() if k not in APPEARANCE}
        atomic_write(WORKSPACE,json.dumps(remaining,indent=2).encode())
    bindings=value.get('keybindings',[])
    path=USER/'keybindings.json'
    if not path.is_symlink() and isinstance(bindings,list) and len(bindings)<=250:atomic_write(path,json.dumps(bindings,indent=2).encode())
    # On builds that store layout server-side, apply only the reviewed UI keys.
    db=USER/'globalStorage/state.vscdb'
    if db.is_file() and not db.is_symlink():
        with sqlite3.connect(db) as connection:
            for key,v in value.get('layout',{}).items():
                if key in LAYOUT_KEYS and isinstance(v,str) and len(v)<=16000:connection.execute('INSERT OR REPLACE INTO ItemTable VALUES (?,?)',(key,v))

def install_extensions(value):
    import os
    import subprocess
    installed=set(export()['extensions'])
    requested=value.get('extensions',[])
    if not isinstance(requested,list) or len(requested)>100:raise ValueError('Invalid extension profile')
    for identity in requested:
        if not isinstance(identity,str) or not re.fullmatch(r'[\w-]+\.[\w-]+',identity):raise ValueError('Invalid extension ID')
        if identity in installed:continue
        # The same reviewed gallery enforces the package/version policy. No
        # external marketplace URL or VSIX path is accepted from preferences.
        subprocess.run(['code-server','--install-extension',identity],check=True,
            env={**os.environ,'EXTENSIONS_GALLERY':json.dumps({'serviceUrl':'http://127.0.0.1:3128/vscode/gallery'})},
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=120)

if __name__=='__main__':
    import sys
    request=json.load(sys.stdin)
    if request['action']=='export':print(json.dumps(export()))
    elif request['action']=='apply':apply(request['profile']);print('{}')
    elif request['action']=='extensions':install_extensions(request['profile']);print('{}')
    else:raise ValueError('Unknown preference operation')
