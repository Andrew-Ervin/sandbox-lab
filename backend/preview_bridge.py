"""Trusted presentation helpers on the untrusted preview origin, never the app origin."""
BRIDGE=b'''<script>(()=>{
let last=0,fit=true,frame=0,applying=false;
function ping(){if(document.hidden||Date.now()-last<5000)return;last=Date.now();parent.postMessage({type:'lab-preview-activity'},'*')}
['pointerdown','keydown','wheel'].forEach(x=>addEventListener(x,ping,{passive:true}));
function init(){
 if(document.documentElement.dataset.labViewer==='image')return;
 let viewport=document.querySelector('meta[name="viewport"]');if(!viewport){viewport=document.createElement('meta');viewport.name='viewport';document.head.append(viewport)}viewport.content='width=device-width,initial-scale=1';
 const style=document.createElement('style');style.textContent='html[data-lab-fit="true"] img,html[data-lab-fit="true"] video{max-width:100%;height:auto}html[data-lab-fit="true"] pre{max-width:100%;overflow:auto}';document.head.append(style);
 const originalZoom=document.body.style.zoom;
 async function resize(){
  if(applying)return;applying=true;
  try{
   document.documentElement.dataset.labFit=String(fit);document.body.style.zoom=originalZoom;
   for(const plot of document.querySelectorAll('.js-plotly-plot')){
    if(!window.Plotly||!plot.layout)continue;
    if(!plot.__labSize)plot.__labSize={width:plot.layout.width,height:plot.layout.height,autosize:plot.layout.autosize};
    if(!plot.__labStyles)plot.__labStyles={width:plot.style.width,height:plot.style.height};
    plot.style.width=fit?'100%':plot.__labStyles.width;
    const signature=String(fit)+':'+innerWidth+':'+plot.parentElement.clientWidth;if(plot.__labFit===signature)continue;plot.__labFit=signature;
    if(fit){const w=Math.max(180,Math.min(innerWidth,plot.parentElement.clientWidth||innerWidth));const original=plot.__labSize;const h=original.width&&original.height?Math.max(260,Math.min(original.height,w*original.height/original.width)):undefined;if(h)plot.style.height=h+'px';await Plotly.relayout(plot,{autosize:true,width:w,...(h?{height:h}:{})});}
    else {plot.style.height=plot.__labStyles.height;await Plotly.relayout(plot,plot.__labSize);}
   }
   if(fit){const width=document.body.scrollWidth;if(width>innerWidth+8)document.body.style.zoom=String(Math.max(.1,innerWidth/width));}
  }finally{applying=false;}
 }
 function schedule(){cancelAnimationFrame(frame);frame=requestAnimationFrame(resize)}
 addEventListener('resize',schedule);addEventListener('load',schedule);addEventListener('lab-fit-change',schedule);
 new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});
 schedule();
}
addEventListener('message',event=>{if(event.source!==parent||event.data?.type!=='lab-preview-fit'||typeof event.data.enabled!=='boolean')return;fit=event.data.enabled;if(document.documentElement.dataset.labViewer==='image'){document.querySelector('[data-zoom="'+(fit?'fit':'1')+'"]')?.click();}else dispatchEvent(new Event('lab-fit-change'));});
if(document.readyState==='loading')addEventListener('DOMContentLoaded',init,{once:true});else init();
})();</script>'''
