import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const context=vm.createContext({ArrayBuffer,DataView});
vm.runInContext(readFileSync('sandbox/pi-dictation/audio.js','utf8'),context);
test('WAV output is mono 16 kHz PCM16 with correct header, length and clipped samples',()=>{
 const bytes=context.labEncodeWav(new Float32Array([-2,-1,0,1,2]));
 const data=new DataView(bytes);const buf=Buffer.from(bytes);
 assert.equal(buf.toString('ascii',0,4),'RIFF');assert.equal(buf.toString('ascii',8,12),'WAVE');
 assert.equal(data.getUint16(20,true),1);assert.equal(data.getUint16(22,true),1);
 assert.equal(data.getUint32(24,true),16000);assert.equal(data.getUint16(34,true),16);
 assert.equal(data.getUint32(40,true),10);assert.equal(bytes.byteLength,54);
 assert.deepEqual([0,1,2,3,4].map(i=>data.getInt16(44+2*i,true)),[-32768,-32768,0,32767,32767]);
});
