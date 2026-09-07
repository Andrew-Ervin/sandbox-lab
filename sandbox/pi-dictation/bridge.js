// LAB_DICTATION_BRIDGE
async function labTranscribeAudio(message,sidebar){
 if(sidebar.labDictationBusy){sidebar.postMessage({type:'dictationResult',id:message.id,error:'A transcription is already in progress.'});return;}
 sidebar.labDictationBusy=true;
 try{
  if(typeof message.data!=='string'||message.data.length>5400000||!['webm','ogg','mp4','wav'].includes(message.format))throw Error('Invalid or oversized recording.');
  const token=require('node:fs').readFileSync(require('node:path').join(require('node:os').homedir(),'.config/lab/token'),'utf8').trim();
  const response=await fetch('http://model-gateway.lab-control.svc.cluster.local:8080/v1/audio/transcriptions',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({data:message.data,format:message.format}),signal:AbortSignal.timeout(90000)});
  const result=await response.json();
  if(!response.ok)throw Error(result.error?.message||'Transcription unavailable.');
  sidebar.postMessage({type:'dictationResult',id:message.id,text:result.text});
 }catch(error){sidebar.postMessage({type:'dictationResult',id:message.id,error:error.name==='TimeoutError'?'Transcription timed out. Try a shorter clip.':error.message||'Transcription failed.'});}
 finally{sidebar.labDictationBusy=false;}
}
