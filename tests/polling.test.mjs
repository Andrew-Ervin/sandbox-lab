import test from 'node:test';
import assert from 'node:assert/strict';
import {startPolling} from '../lib/polling.ts';

const settle = async () => { for (let i=0;i<10;i++) await Promise.resolve(); };
function harness(hidden=false) {
  let now=0, id=0;
  const timers=new Map(), listeners=new Set();
  const visibility={hidden, addEventListener:(_,f)=>listeners.add(f), removeEventListener:(_,f)=>listeners.delete(f)};
  const clock={setTimeout:(f,delay)=>{timers.set(++id,{at:now+delay,f});return id;},clearTimeout:id=>timers.delete(id)};
  return {visibility,clock,timers,listeners,
    show(hidden){visibility.hidden=hidden;for(const f of listeners)f();},
    async advance(ms){
      const end=now+ms;await settle();
      while(true){
        const next=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];
        if(!next)break;
        now=next[1].at;timers.delete(next[0]);next[1].f();await settle();
      }
      now=end;
    },
  };
}
function deferred(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}

test('slow requests never overlap and the next delay starts after completion',async()=>{
  const h=harness(), pending=deferred();let calls=0;
  const stop=startPolling({...h,interval:()=>5000,run:()=>{calls++;return calls===1?pending.promise:Promise.resolve();}});
  await h.advance(20000);assert.equal(calls,1);assert.equal(h.timers.size,0);
  pending.resolve();await h.advance(4999);assert.equal(calls,1);
  await h.advance(1);assert.equal(calls,2);stop();assert.equal(h.timers.size,0);
});

test('hidden views do no work and refresh immediately on return',async()=>{
  const h=harness(true);let calls=0;
  const stop=startPolling({...h,interval:()=>4000,run:async()=>{calls++;}});
  await h.advance(60000);assert.equal(calls,0);
  h.show(false);await settle();assert.equal(calls,1);
  h.show(true);await h.advance(60000);assert.equal(calls,1);
  h.show(false);await settle();assert.equal(calls,2);stop();
});

test('only explicitly configured status polls run in the background',async()=>{
  const h=harness();let calls=0;
  const stop=startPolling({...h,interval:()=>5000,hiddenInterval:30000,run:async()=>{calls++;}});
  await settle();h.show(true);
  await h.advance(29999);assert.equal(calls,1);
  await h.advance(1);assert.equal(calls,2);
  h.show(false);await settle();assert.equal(calls,3);stop();
});

test('visibility changes during a slow request queue one fresh read',async()=>{
  const h=harness(),pending=deferred();let calls=0;
  const stop=startPolling({...h,interval:()=>5000,run:()=>{calls++;return calls===1?pending.promise:Promise.resolve();}});
  h.show(true);h.show(false);h.show(true);h.show(false);
  assert.equal(calls,1);pending.resolve();await h.advance(0);assert.equal(calls,2);
  stop();
});

test('failures back off to 30 seconds and a healthy request resets the delay',async()=>{
  const h=harness();let calls=0,errors=0;
  const stop=startPolling({...h,interval:()=>5000,onError:()=>errors++,run:async()=>{if(++calls<=3)throw Error('offline');}});
  await h.advance(9999);assert.equal(calls,1);
  await h.advance(1);assert.equal(calls,2);
  await h.advance(20000);assert.equal(calls,3);
  await h.advance(30000);assert.equal(calls,4);assert.equal(errors,3);
  await h.advance(5000);assert.equal(calls,5);stop();
});

test('unmount during an outstanding request removes listeners and never reschedules',async()=>{
  const h=harness(),pending=deferred();
  const stop=startPolling({...h,interval:()=>1000,run:()=>pending.promise});
  stop();pending.resolve();await h.advance(60000);
  assert.equal(h.timers.size,0);assert.equal(h.listeners.size,0);
});

test('the active/idle interval can change without restarting an in-flight poll',async()=>{
  const h=harness();let interval=5000,calls=0;
  const stop=startPolling({...h,interval:()=>interval,run:async()=>{calls++;}});
  await settle();interval=30000;
  await h.advance(5000);assert.equal(calls,2);
  await h.advance(29999);assert.equal(calls,2);
  await h.advance(1);assert.equal(calls,3);stop();
});
