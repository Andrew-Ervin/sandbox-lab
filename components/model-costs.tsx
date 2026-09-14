'use client';
import {useEffect,useState} from 'react';
import {startPolling} from '@/lib/polling';
type Period={requests:number;priced_requests:number;pending_requests:number;cost:number|null;input_tokens:number|null;cached_tokens:number|null;output_tokens:number|null};
type Usage={periods:Record<string,Period>;tracking_since:number|null;scope:string};
export function ModelCosts({sessionFetch}:{sessionFetch:(input:RequestInfo|URL,init?:RequestInit)=>Promise<Response>}){
 const [data,setData]=useState<Usage|null>(null),[error,setError]=useState(false);
 useEffect(()=>startPolling({run:async()=>{const r=await sessionFetch('/api/model-usage');if(!r.ok)throw Error();setData(await r.json());setError(false)},interval:()=>60000,onError:()=>setError(true)}),[sessionFetch]);
 return <article className="ops-card"><h2>Model costs</h2><p className="ops-note">All your workspace coding tools · UTC · week starts Monday. Provider-reported costs include cache pricing.</p>{error&&<p role="status">Refresh unavailable; showing the last observation.</p>}<div className="ops-metrics">{Object.entries(data?.periods||{}).map(([key,p])=><div className="ops-metric" key={key}><div>{({today:'Today',week:'This week',month:'This month',year:'Year to date'} as Record<string,string>)[key]}</div><strong>{p.cost==null?'—':`$${p.cost.toFixed(4)}`}</strong><small>{p.priced_requests} priced / {p.requests} requests{p.pending_requests>0?` · ${p.pending_requests} awaiting cost`:''}<br/>{p.cached_tokens==null?'Cache usage unavailable':`${p.cached_tokens.toLocaleString()} cached input tokens`}</small></div>)}</div><p className="ops-note">{data?.tracking_since?`Tracking since ${new Date(data.tracking_since*1000).toLocaleString()}.`:'Tracking begins with your next workspace model request.'} Missing usage is not treated as free. Requests outside this broker and earlier history are not included. Your model budget is separate from Azure.</p></article>
}
