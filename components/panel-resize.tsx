'use client';
import {useRef} from 'react';
import {useSidebar} from '@/components/ui/sidebar';

export function ResizeHandle({side,value,onChange,onReset,min,max,container}:{side:'left'|'right';value:number;onChange:(n:number)=>void;onReset:()=>void;min:number;max:number;container?:()=>HTMLElement|null}) {
 const drag=useRef<{x:number;value:number;unit:number;moved:boolean}|null>(null);
 const clamp=(n:number)=>Math.round(Math.max(min,Math.min(max,n)));
 return <div className={`panel-resizer ${side}`} role="separator" aria-label={side==='left'?'Resize history sidebar':'Resize preview sidebar'} aria-orientation="vertical" aria-valuemin={min} aria-valuemax={max} aria-valuenow={Math.round(value)} tabIndex={0} title="Drag to resize · double-click to reset"
  onPointerDown={e=>{if(e.button!==0)return;e.preventDefault();e.currentTarget.focus();e.currentTarget.setPointerCapture(e.pointerId);drag.current={x:e.clientX,value,unit:side==='right'?100/(container?.()?.clientWidth||1000):1,moved:false};document.documentElement.classList.add('resizing-panels');}}
  onPointerMove={e=>{const d=drag.current;if(!d)return;const delta=e.clientX-d.x;if(Math.abs(delta)>2)d.moved=true;onChange(clamp(d.value+delta*d.unit*(side==='right'?-1:1)));}}
  onLostPointerCapture={()=>{drag.current=null;document.documentElement.classList.remove('resizing-panels');}}
  onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}
  onDoubleClick={onReset}
  onKeyDown={e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();onChange(e.key==='Home'?min:e.key==='End'?max:clamp(value+(e.key==='ArrowRight'?1:-1)*(side==='right'?-1:1)*(side==='left'?16:5)));}}}><span/></div>;
}
export function HistoryResize(props:Omit<Parameters<typeof ResizeHandle>[0],'side'>){const {isMobile,open}=useSidebar();return !isMobile&&open?<ResizeHandle side="left" {...props}/>:null;}
