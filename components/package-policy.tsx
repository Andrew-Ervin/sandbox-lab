'use client';
import {useCallback,useEffect,useState} from 'react';
import {Clock3,Network,ShieldCheck,RefreshCw} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {parsePolicy,type Policy} from '@/lib/package-policy';
export function PackagePolicy({sessionFetch}:{sessionFetch:(input:RequestInfo|URL,init?:RequestInit)=>Promise<Response>}){
 const [policy,setPolicy]=useState<Policy|null>(null),[ecosystem,setEcosystem]=useState('python'),[name,setName]=useState(''),[version,setVersion]=useState(''),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 const load=useCallback(async()=>{try{const r=await sessionFetch('/api/package-policy');if(!r.ok)throw Error('Package policy is unavailable. Please retry.');setPolicy(parsePolicy(await r.json()));setError('');}catch(e){setError((e as Error).message);setPolicy(null);}},[sessionFetch]);
 useEffect(()=>{void load();},[load]);
 const exceptions=(policy?.overrides||[]).filter(x=>x.expires*1000>Date.now());
 return <section className="workspace-page collection-page package-policy">
  <header className="collection-heading"><div><p className="eyebrow">ENVIRONMENT CONTROLS</p><h1>Network & packages</h1><p className="collection-description">Get the packages you need, with a waiting period for new releases.</p></div></header>
  {error?<div className="policy-topline" role="alert"><span>{error}</span><Button variant="ghost" onClick={()=>void load()}><RefreshCw size={15}/> Retry</Button></div>:<div className="policy-topline"><ShieldCheck size={22}/><div><strong>{policy?`${policy.minimum_age_days}-day release delay`:'Loading policy…'}</strong><span> · No package-name whitelist. Exceptions apply to one exact release.</span></div></div>}
  <div className="policy-columns">
   <article className="resource-card"><Network size={22}/><h2>Allowed connections</h2><p>Coder, the model gateway and the read-only package gateway. Direct internet and external DNS are blocked in project workspaces.</p><p>Pi can use Exa search through OpenRouter. Quick Python has no network. MCP and additional destinations are not enabled.</p></article>
   <article className="resource-card"><Clock3 size={22}/><h2>How the waiting period works</h2><p>Python (uv), npm, Cargo and NuGet use publication dates. Go and Julia use a five-day wait from first observation.</p><p>Dependencies follow the same checks. Installed packages remain available. A human-approved exception lasts 24 hours.</p></article>
  </div>
  <form className="resource-card policy-form" onSubmit={async e=>{e.preventDefault();setBusy(true);setMessage('');try{const r=await sessionFetch('/api/package-policy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ecosystem,package:name,version,reason,override_age:true})});const data=await r.json() as {detail?:string;message?:string};if(!r.ok)throw Error(data.detail||'Could not save the exception');setMessage(data.message||'Saved');await load();setName('');setVersion('');setReason('');}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}}>
   <h2>Temporary age exception</h2><p>Allow a specific release before its waiting period ends. Coding agents cannot approve exceptions.</p><div className="policy-fields">
   <label>Ecosystem<select value={ecosystem} onChange={e=>setEcosystem(e.target.value)}>{['python','npm','cargo','go','nuget','julia'].map(x=><option key={x}>{x}</option>)}</select></label>
   <label>Package name<input value={name} onChange={e=>setName(e.target.value)} required placeholder="For example: sympy"/></label>
   <label className="wide">Exact version or Julia content hash<input value={version} onChange={e=>setVersion(e.target.value)} required placeholder="One exact version; no ranges"/></label>
   <label className="wide">Approval reason<textarea value={reason} onChange={e=>setReason(e.target.value)} required minLength={5} maxLength={500} placeholder="Why is this release needed now?"/></label></div>
   <Button disabled={busy||!policy}>{busy?'Applying…':'Allow for 24 hours'}</Button>{message&&<p className="policy-message" role="status">{message}</p>}
  </form>
  {policy&&<section className="policy-exceptions"><h2>Active exceptions <span className="nav-count">{exceptions.length}</span></h2>{!exceptions.length?<p>No exceptions. The standard waiting period applies.</p>:<div className="resource-grid">{exceptions.map((x,i)=><article className="resource-card" key={i}><h2>{x.package} · {x.version}</h2><p>{x.ecosystem} · expires {new Date(x.expires*1000).toLocaleString()}</p><p>{x.reason}</p></article>)}</div>}</section>}
 </section>
}
