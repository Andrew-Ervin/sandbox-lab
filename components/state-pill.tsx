export function StatePill({state}:{state:string}) {
 const labels:Record<string,string>={static:'Saved app',stopped:'Sleeping',unknown:'Unavailable','not started':'Not allocated',running:'Running',starting:'Starting',pending:'Queued',deleting:'Deleting',failed:'Failed'};
 return <span className="state-pill" data-state={state}><i/>{labels[state]||state}</span>;
}
