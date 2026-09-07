import {useState} from 'react';
import {Button} from '@/components/ui/button';

export function ProjectSharing(){
 const [direction,setDirection]=useState('to_chat'),[step,setStep]=useState(0);
 const from=direction==='to_chat'?'Developer workstation':'Chat sandbox',to=direction==='to_chat'?'Chat sandbox':'Developer workstation';
 const steps=[
  ['Separate execution','Each environment has its own namespace, home PVC, credentials, packages and running processes. Linking a workstation alone allocates no chat sandbox.'],
  ['Open and synchronize','Open in VS Code or New chat in project brings eligible source into the destination automatically. A source-bearing developer project gets a separate headless home on chat entry. Empty ordinary chats need none.'],
  ['Keep saved files current','While both sides run, the broker compares manifests every 15 seconds. New files, one-sided edits and tracked deletions propagate. Background checks do not wake sleeping pods or renew activity. Active chat coding finishes before copying.'],
  ['Resolve divergent edits','If both sides changed a file, both versions stay. Choose Keep chat or Keep VS Code in the project. Hash checks protect individual replacements; this is eventual sync, not a multi-file transaction. Restore packages independently from lockfiles.']
 ];
 return <section className="deep">
  <div className="section-label">PROJECTS / SEPARATE EXECUTION · AUTOMATIC SOURCE SYNC</div>
  <h2>One project. Two independent places to work.</h2>
  <p className="lede">Saved source stays synchronized. Chat and VS Code keep separate permissions, dependencies and processes.</p>
  <div className="two"><article>
   <h3>Follow the source</h3>
   <label className="field">Direction<select value={direction} onChange={e=>{setDirection(e.target.value);setStep(0);}}><option value="to_chat">VS Code → Chat</option><option value="to_developer">Chat → VS Code</option></select></label>
   <div className="auth-flow"><span>{from}</span><b>→</b><span>Trusted sync broker</span><b>→</b><span>{to}</span></div>
   <p>Step {step+1} / 4</p><h3>{steps[step][0]}</h3><p>{steps[step][1]}</p>
   <Button onClick={()=>setStep((step+1)%4)}>{step===3?'Start again':'Next step'}</Button>
  </article><article>
   <h3>What crosses the boundary</h3><ul>
    <li>Eligible source and lockfiles: up to 2,000 files, 8 MB/file, 32 MB total and 10,000 scanned entries.</li>
    <li>No installed dependencies, hidden credential paths, symlinks, build output, recursive imports or running processes.</li>
    <li>Fresh projects use project roots; legacy selected import folders keep working. Ongoing sync creates no repeated snapshots.</li>
    <li>Unsaved editor buffers are not copied. Dev servers can require a rebuild or restart after changes.</li>
    <li>Deleting a project removes chats and its headless home; a linked developer workstation is retained and unlinked.</li>
   </ul>
   <div className="callout">Filename filters are not full DLP. Production needs Entra ownership, content policy, durable sync jobs and distributed leases. Use Git revisions for complex collaborative work and avoid concurrent edits to the same files.</div>
  </article></div>
 </section>;
}
