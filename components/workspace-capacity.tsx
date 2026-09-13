'use client';
import {useEffect,useState} from 'react';
import {Button} from '@/components/ui/button';
import {AlertDialog,AlertDialogContent,AlertDialogTitle,AlertDialogDescription,AlertDialogFooter} from '@/components/ui/alert-dialog';
import type {Workspace} from '@/lib/lab-types';
const sizes=[{id:'light',name:'Standard',cpu:1,ram:2,disk:20,cost:.108},{id:'balanced',name:'Build',cpu:2,ram:4,disk:40,cost:.216},{id:'performance',name:'Power',cpu:4,ram:8,disk:80,cost:.432}];
export function WorkspaceCapacity({workspace,sessionFetch,onChanged}:{workspace:Workspace;sessionFetch:(input:RequestInfo|URL,init?:RequestInit)=>Promise<Response>;onChanged:()=>unknown}){
 const [choice,setChoice]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const current=workspace.compute_size||'balanced',selected=sizes.find(s=>s.id===choice);
 useEffect(()=>{setMessage('');setChoice('');},[current]);
 return <div className="workspace-capacity"><label>Compute <select aria-label={`Compute for ${workspace.name}`} value={choice||current} disabled={busy} onChange={e=>{if(e.target.value!==current)setChoice(e.target.value)}}>{sizes.map(s=><option key={s.id} value={s.id}>{s.name} · {s.cpu} CPU / {s.ram} GB · {s.disk} GB disk · ${s.cost.toFixed(3)}/h</option>)}</select></label>
 <Button size="sm" variant="ghost" disabled={busy||workspace.status!=='running'} onClick={async()=>{setBusy(true);try{const r=await sessionFetch(`/api/developer/workspaces/${workspace.id}/preferences`,{method:'POST'});if(!r.ok)throw Error('Open the workspace and retry.');setMessage('Editor preferences saved to your account.');}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}}>Save editor preferences</Button>
 {message&&<p role="status">{message}</p>}
 <AlertDialog open={!!choice} onOpenChange={open=>{if(!open&&!busy)setChoice('')}}><AlertDialogContent><AlertDialogTitle>Change compute for {workspace.name}?</AlertDialogTitle><AlertDialogDescription>The workspace will restart with {selected?.cpu} CPU, {selected?.ram} GB memory, and {selected?.disk} GB disk at ${selected?.cost.toFixed(3)} per active hour. Source files and your portable editor settings move to the new size; processes, package caches, terminals, and unsaved buffers restart. The previous stopped sandbox remains recoverable until it is explicitly removed. Sandbox disk is fixed to the selected compute tier.</AlertDialogDescription><AlertDialogFooter><Button variant="ghost" disabled={busy} onClick={()=>setChoice('')}>Cancel</Button><Button disabled={busy} onClick={async()=>{setBusy(true);setMessage('');try{const r=await sessionFetch(`/api/developer/workspaces/${workspace.id}/compute`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({size:choice})});if(!r.ok)throw Error(((await r.json()) as {detail?:string}).detail||'Could not change compute.');setChoice('');setMessage('Compute updated. Reopen the workspace to continue.');onChanged();}catch(e){setMessage((e as Error).message);setChoice('');}finally{setBusy(false)}}}>{busy?'Changing compute…':'Restart with this size'}</Button></AlertDialogFooter></AlertDialogContent></AlertDialog>
 </div>;
}
