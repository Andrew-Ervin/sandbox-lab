// Share only reviewed editor UI state. Chat data, tokens and workspace storage stay put.
(()=>{
 const profile=__LAB_PROFILE__,keys=__LAB_KEYS__;
 const open=()=>new Promise((resolve,reject)=>{const r=indexedDB.open('vscode-web-state-db-global');r.onupgradeneeded=()=>{if(!r.result.objectStoreNames.contains('ItemTable'))r.result.createObjectStore('ItemTable')};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});
 const read=async db=>{if(!db.objectStoreNames.contains('ItemTable'))return {};const tx=db.transaction('ItemTable','readonly'),store=tx.objectStore('ItemTable');const out={};await Promise.all(keys.map(key=>new Promise(resolve=>{const r=store.get(key);r.onsuccess=()=>{if(typeof r.result==='string'&&r.result.length<=16000)out[key]=r.result;resolve()};r.onerror=resolve})));return out};
 let baseline=null,lastActivity=Date.now(),sentActivity=0;
 for(const event of ['pointerdown','keydown','wheel'])addEventListener(event,()=>{lastActivity=Date.now()},{capture:true,passive:true});
 setInterval(async()=>{if(document.hidden||lastActivity<=sentActivity)return;const stamp=lastActivity;try{const r=await fetch('/__lab/editor-activity',{method:'POST'});if(r.ok)sentActivity=stamp}catch{}},15000);
 (async()=>{
  const db=await open();if(!db.objectStoreNames.contains('ItemTable')){db.close();return}
  const before=await read(db);const wanted=profile||{};
  if(Object.keys(wanted).length&&sessionStorage.getItem('lab-layout-applied')!==JSON.stringify(wanted)){
   const tx=db.transaction('ItemTable','readwrite');for(const key of keys)if(typeof wanted[key]==='string')tx.objectStore('ItemTable').put(wanted[key],key);
   await new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error)});
   const bus=new BroadcastChannel('vscode-web-state-db-global');bus.postMessage({changed:new Map(Object.entries(wanted)),deleted:new Set()});bus.close();sessionStorage.setItem('lab-layout-applied',JSON.stringify(wanted));baseline=JSON.stringify(await read(db));
  }else {baseline=JSON.stringify(before);if(!Object.keys(wanted).length&&Object.keys(before).length){await fetch('/__lab/editor-layout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({layout:before})})}}
  db.close();
 })().catch(()=>{});
 setInterval(async()=>{if(document.hidden||baseline===null)return;try{const db=await open();const layout=await read(db);db.close();const next=JSON.stringify(layout);if(next===baseline)return;const r=await fetch('/__lab/editor-layout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({layout})});if(r.ok)baseline=next}catch{}},15000);
})();
