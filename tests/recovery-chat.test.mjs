import test from 'node:test';
import assert from 'node:assert/strict';
import {consumeEvents,messageRequest,itemText} from '../lib/recovery-chat.ts';
test('new and existing messages use the same authenticated protocol',()=>{
 assert.equal(messageRequest(null,'hi').type,'threads.create');
 assert.equal(messageRequest('thr_a','hi').params.thread_id,'thr_a');
 assert.equal(messageRequest('thr_a','hi').params.input.content[0].text,'hi');
});
test('stream parser handles split event boundaries and unicode',async()=>{
 const bytes=new TextEncoder().encode('data: {"type":"thread.created","thread":{"id":"thr_a"}}\n\ndata: {"text":"é"}\n\ndata: [DONE]\n\n');
 const seen=[];await consumeEvents(new Response(new ReadableStream({start(c){for(const byte of bytes)c.enqueue(Uint8Array.of(byte));c.close();}})),e=>seen.push(e));
 assert.equal(seen.length,2);assert.equal(seen[1].text,'é');
});
test('failed submission is surfaced without replay',async()=>{
 await assert.rejects(consumeEvents(new Response('error',{status:503}),()=>{}),/Check history/);
});
test('widget text is inert and approval actions are not executed',()=>{
 assert.equal(itemText({type:'widget',widget:{type:'Text',value:'<script>bad()</script>',onClick:{type:'approve'}}}),'<script>bad()</script>');
});

test('artifact links are restricted to authenticated file routes',async()=>{
 const {artifactLinks}=await import('../lib/recovery-chat.ts');
 assert.deepEqual(artifactLinks('chatkit-link://file-run_abc-612e747874'),[{name:'a.txt',url:'/api/artifacts/run_abc/a.txt'}]);
 assert.deepEqual(artifactLinks('chatkit-link://file-run_abc-2e2e2f736563726574'),[]);
 assert.deepEqual(artifactLinks('https://evil.test/file-run_abc-612e747874'),[]);
});

test('oversized complete SSE event is rejected before parsing',async()=>{
 const raw='data: '+JSON.stringify({text:'x'.repeat(2_000_001)})+'\n\n';let delivered=false;
 await assert.rejects(consumeEvents(new Response(raw),()=>{delivered=true;}),/recovery limit/);
 assert.equal(delivered,false);
});

test('descending pages become chronological and older overlap is deduplicated',async()=>{
 const {mergeLatestItems,prependOlderItems}=await import('../lib/recovery-chat.ts');
 const current=mergeLatestItems([],[{id:'m4'},{id:'m3'}]);
 assert.equal(current[0].id,'m3');
 assert.deepEqual(prependOlderItems(current,[{id:'m3'},{id:'m2'},{id:'m1'}]).map(x=>x.id),['m1','m2','m3','m4']);
 assert.deepEqual(mergeLatestItems([{id:'m1'},...current],[{id:'m5'},{id:'m4'}]).map(x=>x.id),['m1','m3','m4','m5']);
});
