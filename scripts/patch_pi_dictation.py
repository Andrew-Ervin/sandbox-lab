"""Replace the dictation patch in the reviewed Pi Chat bundle reproducibly."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from backend.limits import value,validate
validate()
constants=f"const LAB_VOICE_SECONDS={value('DICTATION_MAX_SECONDS')},LAB_VOICE_BYTES={value('DICTATION_MAX_BYTES')};\n"
p=root/'sandbox/pi-chat/out/extension.js';s=p.read_text()
if '// LAB_DICTATION_BRIDGE' in s:s=s[:s.index('// LAB_DICTATION_BRIDGE')]
else:
 needle='switch(e.type){case"prompt":'
 if needle not in s:raise RuntimeError('Unexpected Pi Chat bridge bundle')
 s=s.replace(needle,'switch(e.type){case"dictation":await labTranscribeAudio(e,this);break;case"prompt":',1)
bridge=(root/'sandbox/pi-dictation/bridge.js').read_text().replace('// LAB_DICTATION_BRIDGE','// LAB_DICTATION_BRIDGE\n'+constants)
p.write_text(s.rstrip()+'\n'+bridge)
p=root/'sandbox/pi-chat/media/main.js';s=p.read_text();i=s.rindex('})();')
if '// LAB_DICTATION:' in s:
 start=s.index('// LAB_DICTATION:');s=s[:start]+s[i:];i=start
patch=(root/'sandbox/pi-dictation/client.js').read_text()
line=patch.index('\n');patch=patch[:line+1]+constants+(root/'sandbox/pi-dictation/audio.js').read_text()+'\n'+patch[line+1:]
p.write_text(s[:i]+patch+'\n'+s[i:])
