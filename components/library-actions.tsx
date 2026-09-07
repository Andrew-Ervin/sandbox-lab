'use client';
import {createContext,useContext,useState,type ReactNode} from 'react';
import {Archive,ArchiveRestore,FolderOpen,MoreHorizontal,Pencil,Plus,Trash2,LoaderCircle} from 'lucide-react';
import {DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,DropdownMenuSeparator} from '@/components/ui/dropdown-menu';
import {AlertDialog,AlertDialogContent,AlertDialogTitle,AlertDialogDescription,AlertDialogFooter} from '@/components/ui/alert-dialog';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import type {Project,ChatSummary} from '@/lib/lab-types';

type Target={kind:'project'|'chat';id:string;name:string;archived?:boolean};
type Change={kind:Target['kind'];id:string;action:'archive'|'restore'|'delete'|'rename'};
type Actions={archive:(target:Target)=>void;confirm:(target:Target,action:'delete'|'rename')=>void};
const Context=createContext<Actions|null>(null);
export const useLibraryActions=()=>useContext(Context)!;
export function LibraryActions({children,sessionFetch,onChanged,onError}:{children:ReactNode;sessionFetch:(input:RequestInfo|URL,init?:RequestInit)=>Promise<Response>;onChanged:(change:Change)=>unknown;onError:(message:string)=>void}){
 const [dialog,setDialog]=useState<{target:Target;action:'delete'|'rename'}|null>(null);
 const [name,setName]=useState('');const [confirmation,setConfirmation]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 const path=(target:Target)=>`/api/${target.kind==='project'?'projects':'threads'}/${target.id}`;
 async function request(target:Target,method:string,body?:unknown){const r=await sessionFetch(path(target),{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json().catch(()=>({})) as {status?:string;detail?:string};if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Could not save this change. Please retry.');return data;}
 async function archive(target:Target){try{await request(target,'PATCH',{archived:!target.archived});await onChanged({kind:target.kind,id:target.id,action:target.archived?'restore':'archive'});}catch(e){onError((e as Error).message);}}
 async function submit(){if(!dialog||busy||(dialog.action==='delete'&&dialog.target.kind==='project'&&confirmation.trim()!==dialog.target.name))return;setBusy(true);setError('');try{
   if(dialog.action==='rename')await request(dialog.target,'PATCH',{name:name.trim()});
   else await request(dialog.target,'DELETE',dialog.target.kind==='project'?{name:confirmation.trim()}:undefined);
   await onChanged({kind:dialog.target.kind,id:dialog.target.id,action:dialog.action});setDialog(null);
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <Context.Provider value={{archive:target=>void archive(target),confirm:(target,action)=>{setDialog({target,action});setName(target.name);setConfirmation('');setError('');}}}>{children}
   <AlertDialog open={!!dialog} onOpenChange={open=>{if(!open&&!busy)setDialog(null);}}><AlertDialogContent className="library-dialog">
     <AlertDialogTitle>{dialog?.action==='rename'?'Rename project':`Delete ${dialog?.target.kind}?`}</AlertDialogTitle>
     <AlertDialogDescription>{dialog?.action==='rename'?'Choose a name that makes this project easy to find.':dialog?.target.kind==='project'?`“${dialog.target.name}” and its conversations, chat apps, chat sandbox files and mock OneDrive copy will be permanently deleted. Any linked developer workstation is retained and unlinked. This cannot be undone.`:`“${dialog?.target.name}” and its conversation outputs will be permanently deleted. Shared project workspace files are kept.`}</AlertDialogDescription>
     {dialog?.action==='rename'&&<form id="rename-project-form" onSubmit={e=>{e.preventDefault();void submit();}}><label htmlFor="project-name">Project name</label><Input id="project-name" autoFocus maxLength={120} value={name} onChange={e=>setName(e.target.value)} disabled={busy}/></form>}
     {dialog?.action==='delete'&&dialog.target.kind==='project'&&<div><label htmlFor="confirm-project-name">Type <strong>{dialog.target.name}</strong> to confirm</label><Input id="confirm-project-name" autoComplete="off" onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();void submit();}}} value={confirmation} onChange={e=>setConfirmation(e.target.value)} disabled={busy}/></div>}
     {busy&&dialog?.action==='delete'&&<p className="library-progress" role="status"><LoaderCircle size={15} className="spin"/> {dialog.target.kind==='project'?'Submitting deletion…':'Deleting conversation…'}</p>}
     {error&&<p role="alert" className="project-error">{error}</p>}
     <AlertDialogFooter><Button variant="ghost" disabled={busy} onClick={()=>setDialog(null)}>Cancel</Button><Button variant={dialog?.action==='delete'?'destructive':'default'} disabled={busy||(dialog?.action==='rename'&&!name.trim())||(dialog?.action==='delete'&&dialog.target.kind==='project'&&confirmation.trim()!==dialog.target.name)} onClick={()=>void submit()}>{busy?'Working…':dialog?.action==='rename'?'Save name':'Delete permanently'}</Button></AlertDialogFooter>
   </AlertDialogContent></AlertDialog>
 </Context.Provider>;
}
export function ProjectMenu({project,onOpen,onNewChat}:{project:Project;onOpen:()=>void;onNewChat:()=>void}){
 const actions=useLibraryActions();const target:Target={kind:'project',id:project.id,name:project.name,archived:project.archived};
 return <DropdownMenu><DropdownMenuTrigger className="row-action menu-trigger" aria-label={`Options for ${project.name}`} title="Project options"><MoreHorizontal size={17}/></DropdownMenuTrigger><DropdownMenuContent className="library-menu" side="bottom" align="end">
   <div className="library-menu-summary"><strong>{project.name}</strong><span>{project.threads.length} conversation{project.threads.length===1?'':'s'} · {project.deleting?'Deleting':project.archived?'Archived':project.status}</span></div>
   <DropdownMenuSeparator/>
   <DropdownMenuItem onClick={onOpen}><FolderOpen/> {project.archived?'View project':'Open project & files'}</DropdownMenuItem>
   <DropdownMenuItem disabled={project.archived||project.deleting} onClick={onNewChat}><Plus/> New chat in project</DropdownMenuItem>
   <DropdownMenuItem disabled={project.deleting} onClick={()=>actions.confirm(target,'rename')}><Pencil/> Rename project</DropdownMenuItem>
   <DropdownMenuSeparator/>
   <DropdownMenuItem disabled={project.deleting} onClick={()=>actions.archive(target)}>{project.archived?<ArchiveRestore/>:<Archive/>}{project.archived?'Restore project':'Archive project'}</DropdownMenuItem>
   <DropdownMenuItem variant="destructive" disabled={project.deleting&&project.deletion?.status!=='failed'} onClick={()=>actions.confirm(target,'delete')}><Trash2/> {project.deletion?.status==='failed'?'Retry deletion…':project.deleting?'Deleting in background…':'Delete project…'}</DropdownMenuItem>
 </DropdownMenuContent></DropdownMenu>;
}
export function ChatActions({chat,quickArchive=false}:{chat:ChatSummary;quickArchive?:boolean}){
 const actions=useLibraryActions();const target:Target={kind:'chat',id:chat.id,name:chat.title,archived:chat.archived};
 return <div className="chat-row-actions">{quickArchive&&<button className="row-action quick-archive" aria-label={`Archive ${chat.title}`} title="Archive chat" onClick={()=>actions.archive(target)}><Archive size={15}/></button>}<DropdownMenu><DropdownMenuTrigger className="row-action menu-trigger" aria-label={`Options for conversation ${chat.title}`} title="Chat options"><MoreHorizontal size={16}/></DropdownMenuTrigger><DropdownMenuContent className="library-menu" align="end">
 <DropdownMenuItem onClick={()=>actions.archive(target)}>{chat.archived?<ArchiveRestore/>:<Archive/>}{chat.archived?'Restore chat':'Archive chat'}</DropdownMenuItem><DropdownMenuItem variant="destructive" onClick={()=>actions.confirm(target,'delete')}><Trash2/> Delete chat…</DropdownMenuItem>
 </DropdownMenuContent></DropdownMenu></div>;
}

export function ArchiveNotice({chat,project}:{chat?:ChatSummary;project?:Project}){
 const actions=useLibraryActions();
 if(!chat?.archived&&!project?.archived)return null;
 const target:Target=project?.archived?{kind:'project',id:project.id,name:project.name,archived:true}:{kind:'chat',id:chat!.id,name:chat!.title,archived:true};
 return <div className="chat-archive-notice"><Archive size={15}/><span>This {target.kind==='chat'?'conversation':'project'} is archived. Restore it to continue.</span><Button variant="ghost" size="sm" onClick={()=>actions.archive(target)}>Restore {target.kind}</Button></div>;
}
