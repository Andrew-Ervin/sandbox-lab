import {build} from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';
const root=process.cwd();
const tasks=process.argv.slice(2);
for(const name of tasks.length?tasks:['sidebar','report']){
 const entry=name==='sidebar'?'sandbox/vscode-agent/chat.tsx':'reports/architecture/main.tsx';
 const out=path.join(root,'.local/embeds',name);
 await build({configFile:false,plugins:[react()],define:{'process.env.NODE_ENV':'"production"'},resolve:{alias:{'@':root}},build:{minify:true,outDir:out,emptyOutDir:true,lib:{entry:path.join(root,entry),name:'LabEmbed',formats:['iife'],fileName:()=> 'app.js',cssFileName:'app'},cssCodeSplit:false,rollupOptions:{output:{inlineDynamicImports:true}}}});
 if(name==='sidebar')for(const [a,b]of[['app.js','chat.js'],['app.css','chat.css']])fs.copyFileSync(path.join(out,a),path.join(root,'sandbox/vscode-agent',b));
 else{
 const js=fs.readFileSync(path.join(out,'app.js'),'utf8').replaceAll('</script','<\\/script');
 const css=fs.readFileSync(path.join(out,'app.css'),'utf8');
 fs.writeFileSync(path.join(root,'reports/architecture/architecture.html'),'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sandbox Lab — Field guide</title><style>'+css+'</style></head><body><div id="root"></div><script>'+js+'</script></body></html>');
 }
}
