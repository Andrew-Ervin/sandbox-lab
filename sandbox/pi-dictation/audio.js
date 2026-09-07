// Encode the browser recording as the provider-tested mono PCM WAV format.
function labEncodeWav(samples) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const label = (offset, value) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  label(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true);
  label(8, 'WAVE'); label(12, 'fmt '); view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  label(36, 'data'); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
  }
  return buffer;
}

async function labRecordingWav(blob) {
  const context = new AudioContext();
  let decoded;
  try { decoded = await context.decodeAudioData(await blob.arrayBuffer()); }
  finally { await context.close(); }
  if (!decoded.length || decoded.duration > LAB_VOICE_SECONDS + 2) throw Error('Recording exceeds the dictation time limit.');
  const renderer = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
  const source = renderer.createBufferSource(); source.buffer = decoded;
  source.connect(renderer.destination); source.start();
  const audio = await renderer.startRendering();
  return new Blob([labEncodeWav(audio.getChannelData(0))], {type: 'audio/wav'});
}
