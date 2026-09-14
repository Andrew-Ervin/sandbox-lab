'use client';
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { artifactLinks, consumeEvents, itemText, messageRequest, mergeLatestItems, prependOlderItems } from '@/lib/recovery-chat';

export function RecoveryChat({ thread, sessionFetch, onThread, onRefresh, onFullView }: {
  thread: string | null; sessionFetch: typeof fetch; onThread: (id: string) => void;
  onRefresh: () => void; onFullView: () => void;
}) {
  const [items, setItems] = useState<any[]>([]), [draft, setDraft] = useState('');
  const [itemsThread,setItemsThread]=useState<string | null>(null);
  const [loading, setLoading] = useState(false), [sending, setSending] = useState(false);
  const [error, setError] = useState(''), [locked, setLocked] = useState(false);
  const [readError,setReadError]=useState('');
  const [hasMore,setHasMore]=useState(false);
  const firstPage = useRef(true);
  const drafts = useRef(new Map<string,string>());
  const selected = useRef(thread), generation = useRef(0), submitting = useRef(false);
  selected.current = thread;
  const read = async (id: string, version: number) => {
    const response = await sessionFetch('/api/chatkit', { method: 'POST', signal: AbortSignal.timeout(12000), headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({type:'threads.get_by_id',params:{thread_id:id}}) });
    if (!response.ok) throw Error(`Conversation could not load (${response.status}).`);
    const data: any = await response.json();
    const page = await sessionFetch('/api/chatkit', {method:'POST',signal:AbortSignal.timeout(12000),headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'items.list',params:{thread_id:id,order:'desc',limit:100}})});
    if(!page.ok)throw Error('Conversation messages could not load.');
    data.items=await page.json();
    if (generation.current === version && selected.current === id) {
      setReadError('');
      setItemsThread(id);setItems(current=>mergeLatestItems(current,data.items?.data || []));if(firstPage.current){setHasMore(Boolean(data.items?.has_more));firstPage.current=false;} setLocked(data.status?.type === 'locked');
    }
  };
  useEffect(() => {
    const version = ++generation.current;
    if(!thread)setItemsThread(null);
    firstPage.current=true;setItems([]); setHasMore(false); setError(''); setReadError(''); setDraft(drafts.current.get(thread || 'new') || ''); setLocked(false); setLoading(Boolean(thread));
    let active = true, timer: ReturnType<typeof setTimeout>;
    const update = async () => {
      try { if (thread) await read(thread, version); }
      catch (e) { if(active) setReadError((e as Error).message); }
      finally { if(active) {setLoading(false); timer=setTimeout(update, 1500);} }
    };
    if(thread) void update();
    return () => {active=false; clearTimeout(timer); generation.current++;};
  }, [thread, sessionFetch]);
  const older = async () => {
    if(!thread || !items.length)return;
    const id=thread,version=generation.current;
    try {
      const response=await sessionFetch('/api/chatkit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'items.list',params:{thread_id:id,after:items[0].id,order:'desc',limit:100}})});
      if(!response.ok)throw Error('Earlier messages could not load.');
      const data: any=await response.json();
      if(generation.current===version){setItems(current=>prependOlderItems(current,data.data));setHasMore(data.has_more);}
    }catch(e){setError((e as Error).message);}
  };
  const send = async () => {
    if (submitting.current || locked || !draft.trim()) return;
    submitting.current=true; setSending(true); setError('');
    const original=thread, text=draft, submitVersion=generation.current; let created: string | null=null;
    setDraft('');drafts.current.delete(thread || 'new');
    try {
      const response=await sessionFetch('/api/chatkit',{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Mode':'auto'},body:JSON.stringify(messageRequest(original,text))});
      await consumeEvents(response,event=>{
        if(event.type==='thread.created') {
          created=event.thread.id;
          if(selected.current===original && generation.current===submitVersion) onThread(event.thread.id);
          onRefresh();
        }
        if(event.type==='error') throw Error(event.message || 'Response failed. Check saved history before retrying.');
      });
      const id=created || original;
      if(id && selected.current===id) await read(id,generation.current);
      onRefresh();
    } catch(e) {if(selected.current===(created || original))setError((e as Error).message+' The message was not automatically resent.');onRefresh();}
    finally {submitting.current=false;setSending(false);}
  };
  const waiting=loading || itemsThread!==thread;
  return <section className="recovery-chat" aria-label="Recovery chat">
    <div className="recovery-banner"><span>Reliable text view · saved messages use the same conversation. Interactive cards are available in the full view.</span><Button variant="outline" size="sm" onClick={onFullView} disabled={sending}>Try full view</Button></div>
    <div className="recovery-messages" aria-busy={waiting}>
      {!waiting && hasMore && <Button variant="outline" onClick={()=>void older()}>Load earlier messages</Button>}
      {waiting ? <p role="status">Loading conversation…</p> : items.map(item=>{const text=itemText(item);return text ? <article key={item.id} className={item.type==='user_message'?'recovery-user':''}><strong>{item.type==='user_message'?'You':'Assistant'}</strong><div className="whitespace-pre-wrap break-words">{text}</div>{artifactLinks(text).map(link=><a key={link.url} className="underline" href={link.url} download>Download {link.name}</a>)}</article>:null;})}
      {!thread && !waiting && <p>What do you want to work on?</p>}
    </div>
    {error && <p role="alert">{error}</p>}
    {readError && <p role="alert">{readError} Retrying…</p>}
    {(sending || locked) && <p role="status">Response running. You can switch conversations; the job continues.</p>}
    <form onSubmit={e=>{e.preventDefault();void send();}} className="recovery-composer">
      <textarea aria-label="Message" value={draft} onChange={e=>{setDraft(e.target.value);drafts.current.set(thread || 'new',e.target.value);}} maxLength={30000} placeholder="Message Sandbox Lab" disabled={waiting || sending}/>
      <Button type="submit" disabled={waiting || sending || locked || !draft.trim()}>Send</Button>
    </form>
  </section>;
}
