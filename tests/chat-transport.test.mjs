import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ChatTransport} from '../lib/chat-transport.ts';
const request=id=>({body:JSON.stringify({type:id?'threads.add_user_message':'threads.create',params:id?{thread_id:id}:{}})});
test('submission locks immediately, streams without buffering, and releases on completion',async()=>{
 const transport=new ChatTransport();let controller;
 const fetcher=async()=>new Response(new ReadableStream({start(c){controller=c;}}));
 const response=await transport.send(fetcher,'/api/chatkit',request('A'));
 assert.equal(transport.busy('A'),true);
 await assert.rejects(transport.send(fetcher,'/api/chatkit',request('A')),/already responding/);
 const reader=response.body.getReader();controller.enqueue(new TextEncoder().encode('first chunk'));
 assert.equal(new TextDecoder().decode((await reader.read()).value),'first chunk');
 controller.close();await reader.read();assert.equal(transport.busy('A'),false);
});
test('new conversation binds its server ID, while another conversation remains independent',async()=>{
 const transport=new ChatTransport();let c;
 const response=await transport.send(async()=>new Response(new ReadableStream({start(x){c=x;}})),'/',request());
 const reader=response.body.getReader();c.enqueue(new TextEncoder().encode('data: {"type":"thread.created","thread":{"id":"A"}}\n\n'));
 await reader.read();assert.equal(transport.busy('A'),true);assert.equal(transport.busy(null),false);
 const other=await transport.send(async()=>new Response('done'),'/',request('B'));
 await other.text();assert.equal(transport.busy('B'),false);
 await reader.cancel();assert.equal(transport.busy('A'),false);
});
test('navigation detaches a rebound stream and releases the UI without waiting for the job',async()=>{
 const transport=new ChatTransport();let controller,canceled=false;
 const response=await transport.send(async()=>new Response(new ReadableStream({start(c){controller=c;},cancel(){canceled=true;}})),'/',request());
 const reader=response.body.getReader();controller.enqueue(new TextEncoder().encode('data: {"type":"thread.created","thread":{"id":"A"}}\n\n'));
 await reader.read();
 await transport.detach();
 assert.equal(canceled,true);assert.equal(transport.busy('A'),false);
 assert.equal((await reader.read()).done,true);
});
test('a stuck upstream cancellation does not block navigating away',async()=>{
 const transport=new ChatTransport();
 await transport.send(async()=>new Response(new ReadableStream({cancel(){return new Promise(()=>{});}})),'/',request('A'));
 await transport.detach();
 assert.equal(transport.busy('A'),false);
});
test('navigation also detaches before response headers arrive',async()=>{
 const transport=new ChatTransport();let finish;
 const pending=transport.send(()=>new Promise(resolve=>{finish=resolve;}),'/',request('A'));
 assert.equal(transport.busy('A'),true);
 await transport.detach();
 assert.equal(transport.busy('A'),false);
 finish(new Response('late stream'));
 await assert.rejects(pending,{name:'AbortError'});
});
