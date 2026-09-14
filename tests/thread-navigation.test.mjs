import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ThreadNavigation} from '../lib/thread-navigation.ts';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};
test('slow older selection cannot finish after newest selection',async()=>{
 const nav=new ThreadNavigation(),first=deferred(),calls=[],done=[];
 const a=nav.select('old',async id=>{calls.push(id);await first.promise},()=>done.push('old'));
 await Promise.resolve();await Promise.resolve();
 nav.select('skip',async id=>calls.push(id),()=>done.push('skip'));
 const b=nav.select(null,async id=>calls.push(id),()=>done.push('new'));
 first.resolve();await Promise.all([a,b]);
 assert.deepEqual(calls,['old',null]);assert.deepEqual(done,['new']);
});
test('failed selection releases queue for recovery without stale error',async()=>{
 const nav=new ThreadNavigation(),first=deferred(),errors=[];
 const a=nav.select('old',()=>first.promise,e=>errors.push(e));
 await Promise.resolve();await Promise.resolve();
 const b=nav.select('next',async()=>{},e=>errors.push(e));
 first.reject(Error('stale'));await Promise.all([a,b]);assert.deepEqual(errors,[undefined]);
});
test('command acknowledgement alone does not release a pending content load',async()=>{
 const nav=new ThreadNavigation(),loaded=deferred(),calls=[];
 const first=nav.select('A',async()=>{await Promise.resolve();await loaded.promise},()=>calls.push('A done'));
 await Promise.resolve();await Promise.resolve();
 const next=nav.select('B',async()=>calls.push('B requested'),()=>calls.push('B done'));
 await Promise.resolve();assert.deepEqual(calls,[]);
 loaded.resolve();await Promise.all([first,next]);assert.deepEqual(calls,['B requested','B done']);
});
