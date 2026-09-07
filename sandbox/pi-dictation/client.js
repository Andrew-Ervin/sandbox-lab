  // LAB_DICTATION: opt-in recording, editable transcript, no automatic chat send.
  const mic = document.createElement('button');
  mic.id='btn-mic'; mic.className='icon-button'; mic.type='button';
  mic.title='Dictate with OpenRouter (ZDR)'; mic.setAttribute('aria-label','Start dictation');
  mic.innerHTML='<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/></svg>';
  btnAttach.after(mic);
  const voiceStatus=document.createElement('div');voiceStatus.setAttribute('role','status');voiceStatus.style.cssText='font-size:12px;padding:6px 10px;color:var(--vscode-descriptionForeground);display:none';
  const voiceText=document.createElement('span');const voiceCancel=document.createElement('button');voiceCancel.textContent='Cancel';voiceCancel.className='icon-button';voiceCancel.style.marginLeft='8px';voiceStatus.append(voiceText,voiceCancel);$('input-area').append(voiceStatus);
  let recorder=null,stream=null,voiceTimer=null,voiceId=null,voiceCancelled=false,voiceChunks=[],voiceBytes=0;
  function voiceMessage(text){voiceText.textContent=text;voiceStatus.style.display=text?'':'none';}
  function releaseVoice(){clearTimeout(voiceTimer);if(stream)stream.getTracks().forEach(t=>t.stop());stream=null;mic.style.color='';mic.setAttribute('aria-label','Start dictation');}
  function cancelVoice(){voiceCancelled=true;voiceId=null;if(recorder?.state==='recording')recorder.stop();releaseVoice();voiceChunks=[];mic.disabled=false;voiceMessage('');}
  voiceCancel.onclick=cancelVoice;
  mic.onclick=async()=>{
    if(recorder?.state==='recording'){recorder.stop();releaseVoice();return;}
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){voiceMessage('Microphone unavailable. Use HTTPS or localhost and allow microphone access.');return;}
    voiceCancelled=false;voiceId=crypto.randomUUID();const id=voiceId;mic.disabled=true;
    try{
      stream=await navigator.mediaDevices.getUserMedia({audio:true});
      if(id!==voiceId){releaseVoice();return;}
      const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
      if(!mime)throw new Error('No supported recording format in this browser.');
      recorder=new MediaRecorder(stream,{mimeType:mime,audioBitsPerSecond:64000});voiceChunks=[];voiceBytes=0;
      recorder.ondataavailable=e=>{if(e.data.size){voiceBytes+=e.data.size;if(voiceBytes>4000000){cancelVoice();voiceMessage('Recording too large. Try a shorter clip.');return;}voiceChunks.push(e.data);}};
      recorder.onerror=()=>{cancelVoice();voiceMessage('Recording failed. Try again.');};
      recorder.onstop=async()=>{
        releaseVoice();if(voiceCancelled||id!==voiceId)return;
        mic.disabled=true;voiceMessage('Transcribing with OpenRouter · ZDR…');
        const blob=new Blob(voiceChunks,{type:mime});voiceChunks=[];
        const reader=new FileReader();reader.onload=()=>{if(id===voiceId)vscode.postMessage({type:'dictation',id,data:String(reader.result).split(',')[1],format:mime.includes('webm')?'webm':mime.includes('ogg')?'ogg':'mp4'});};reader.onerror=()=>{cancelVoice();voiceMessage('Could not read recording.');};reader.readAsDataURL(blob);
      };
      recorder.start(1000);mic.disabled=false;mic.style.color='var(--vscode-errorForeground)';mic.setAttribute('aria-label','Stop dictation');voiceMessage('Recording · click microphone to transcribe · 5 minutes maximum');voiceTimer=setTimeout(()=>{if(recorder?.state==='recording')recorder.stop();releaseVoice();},300000);
    }catch(error){cancelVoice();voiceMessage(error.name==='NotAllowedError'?'Microphone permission denied. Allow microphone access for this workspace in your browser.':error.message||'Microphone unavailable.');}
  };
  window.addEventListener('message',event=>{
    const msg=event.data;
    if(msg.type==='sessionCleared'){cancelVoice();return;}
    if(msg.type!=='dictationResult'||msg.id!==voiceId)return;
    voiceId=null;mic.disabled=false;
    if(msg.error){voiceMessage(msg.error);return;}
    inputEl.value+=(inputEl.value?' ':'')+(msg.text||'');inputEl.dispatchEvent(new Event('input'));inputEl.focus();voiceMessage(msg.text?'Dictation added. Review it before sending.':'No speech detected.');
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&recorder?.state==='recording')cancelVoice();});
  window.addEventListener('pagehide',cancelVoice);
