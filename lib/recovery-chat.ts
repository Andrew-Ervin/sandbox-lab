// Recovery uses the same authenticated ChatKit protocol, never a second job API.
export function messageRequest(thread: string | null, text: string) {
  const input = { content: [{ type: 'input_text', text }], attachments: [], inference_options: {} };
  return { type: thread ? 'threads.add_user_message' : 'threads.create', params: thread ? { thread_id: thread, input } : { input } };
}
export async function consumeEvents(response: Response, receive: (event: any) => void) {
  if (!response.ok) throw Error(`Chat request failed (${response.status}). Check history before retrying.`);
  if (!response.body) throw Error('Chat response was empty. Check history before retrying.');
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      if (buffer.length > 2_000_000) throw Error('Chat event exceeds the recovery limit. Reopen history.');
      const frames = buffer.replace(/\r\n/g, '\n').split('\n\n');
      buffer = frames.pop() || '';
      for (const frame of frames) {
        const data = frame.split('\n').filter(x => x.startsWith('data:')).map(x => x.slice(5).trimStart()).join('\n');
        if (data && data !== '[DONE]') receive(JSON.parse(data));
      }
      if (buffer.length > 2_000_000) throw Error('Chat event exceeds the recovery limit. Reopen history.');
    }
  } finally { reader.releaseLock(); }
}
export function itemText(item: any): string {
  if (item.type === 'user_message' || item.type === 'assistant_message') return (item.content || []).map((p: any) => p.text || '').join('\n');
  // Never interpret widget data as HTML or synthesize approval actions.
  if (item.type === 'widget') {
    const texts: string[] = [];
    const visit = (node: any, depth = 0) => {
      if (!node || typeof node !== 'object' || depth > 20) return;
      if (typeof node.value === 'string' && ['Text', 'Caption', 'Markdown'].includes(node.type)) texts.push(node.value);
      if (Array.isArray(node.children)) node.children.forEach((c: any) => visit(c, depth + 1));
    };
    visit(item.widget); return texts.join('\n') || 'Result or approval card. Use the full view for interactive controls.';
  }
  return '';
}

export function artifactLinks(text: string): {name:string;url:string}[] {
  const links: {name:string;url:string}[]=[];
  for(const match of text.matchAll(/chatkit-link:\/\/file-(run_[a-f0-9]+)-([a-f0-9]+)/g)) {
    try {
      if(match[2].length % 2 || match[2].length > 640) continue;
      const name=new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(match[2].match(/../g)!,x=>parseInt(x,16)));
      if(!/^[A-Za-z0-9][A-Za-z0-9_. -]{0,159}$/.test(name) || name.includes('..'))continue;
      const url=`/api/artifacts/${match[1]}/${encodeURIComponent(name)}`;
      if(!links.some(x=>x.url===url))links.push({name,url});
    }catch{}
  }
  return links;
}

export function mergeLatestItems(current: any[], descending: any[]): any[] {
  const latest=[...descending].reverse(), ids=new Set(latest.map(i=>i.id));
  return [...current.filter(i=>!ids.has(i.id)),...latest];
}
export function prependOlderItems(current: any[], descending: any[]): any[] {
  const ids=new Set(current.map(i=>i.id));
  return [...[...descending].reverse().filter(i=>!ids.has(i.id)),...current];
}
