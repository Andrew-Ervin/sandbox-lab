'use client';
import {useEffect,useState} from 'react';
import {Button} from '@/components/ui/button';
import {AlertDialog,AlertDialogContent,AlertDialogTitle,AlertDialogDescription,AlertDialogFooter} from '@/components/ui/alert-dialog';
import type {Workspace} from '@/lib/lab-types';
const sizes=[{id:'light',name:'Light',cpu:1,ram:2,cost:.108},{id:'balanced',name:'Balanced',cpu:2,ram:4,cost:.216},{id:'performance',name:'Performance',cpu:4,ram:8,cost:.432}];
export function WorkspaceCapacity({workspace,sessionFetch,onChanged}:{workspace:Workspace;sessionFetch:(input:RequestInfo|URL,init?:RequestInit)=>Promise<Response>;onChanged:()=>unknown}){
 const [choice,setChoice]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const current=workspace.compute_size||'performance',selected=sizes.find(s=>s.id===choice);
 useEffect(()=>setMessage(''),[current]);
 return <div className="workspace-capacity"><label>Compute <select aria-label={`Compute for ${workspace.name}`} value={current} disabled={busy} onChange={e=>setChoice(e.target.value)}>{sizes.map(s=><option key={s.id} value={s.id}>{s.name} · {s.cpu} CPU / {s.ram} GB · ${s.cost.toFixed(3)}/h</option>)}</select></label>
 <Button size="sm" variant="ghost" disabled={busy||workspace.status!=='running'} onClick={async()=>{setBusy(true);try{const r=await sessionFetch(`/api/developer/workspaces/${workspace.id}/preferences`,{method:'POST'});if(!r.ok)throw Error('Open the workspace and retry.');setMessage('Editor preferences saved to your account.');}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}}>Save editor preferences</Button>
 {message&&<p role="status">{message}</p>}
 <AlertDialog open={!!choice} onOpenChange={open=>{if(!open&&!busy)setChoice('')}}><AlertDialogContent><AlertDialogTitle>Change compute for {workspace.name}?</AlertDialogTitle><AlertDialogDescription>Save your files first. The workspace will restart with {selected?.cpu} CPU and {selected?.ram} GB memory at ${selected?.cost.toFixed(3)} per active hour. Saved state is retained. The testing budget still applies. This service supports up to 4 CPU and 8 GB; compute does not resize automatically.</AlertDialogDescription><AlertDialogFooter><Button variant="ghost" disabled={busy} onClick={()=>setChoice('')}>Cancel</Button><Button disabled={busy} onClick={async()=>{setBusy(true);setMessage('');try{const r=await sessionFetch(`/api/developer/workspaces/${workspace.id}/compute`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({size:choice})});if(!r.ok)throw Error(((await r.json()) as {detail?:string}).detail||'Could not change compute.');setChoice('');setMessage('Compute updated. Reopen the workspace to continue.');onChanged();}catch(e){setMessage((e as Error).message);setChoice('');}finally{setBusy(false)}}}>{busy?'Changing compute…':'Restart with this size'}</Button></AlertDialogFooter></AlertDialogContent></AlertDialog>
 </div>;
}
