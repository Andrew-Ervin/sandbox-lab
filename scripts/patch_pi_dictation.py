"""Idempotent dictation patch for the reviewed Pi Chat bundle."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'sandbox/pi-chat/out/extension.js';s=p.read_text()
if '// LAB_DICTATION_BRIDGE' not in s:
 needle='switch(e.type){case"prompt":'
 if needle not in s:raise RuntimeError('Unexpected Pi Chat bridge bundle')
 s=s.replace(needle,'switch(e.type){case"dictation":await labTranscribeAudio(e,this);break;case"prompt":',1)
 s+='\n'+(root/'sandbox/pi-dictation/bridge.js').read_text();p.write_text(s)
p=root/'sandbox/pi-chat/media/main.js';s=p.read_text()
if '// LAB_DICTATION:' not in s:
 i=s.rindex('})();');s=s[:i]+(root/'sandbox/pi-dictation/client.js').read_text()+'\n'+s[i:];p.write_text(s)
