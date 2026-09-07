// Reviewed upstream UI, pinned source; local patches only integrate the lab boundary.
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {build} from 'esbuild';
const root=process.cwd(),source=path.join(root,'.local/vendor/pi-vscode-chat'),out=path.join(root,'sandbox/pi-chat');
const commit='7254553b9b8fcb8701920693c56c3af2be9b317e';
if(execFileSync('git',['-C',source,'rev-parse','HEAD'],{encoding:'utf8'}).trim()!==commit)throw Error('Unexpected upstream Pi Chat revision');
fs.mkdirSync(path.join(out,'media'),{recursive:true});fs.mkdirSync(path.join(out,'out'),{recursive:true});
const scratch=path.join(root,'.local/vendor/pi-chat-patched');fs.mkdirSync(scratch,{recursive:true});
fs.cpSync(path.join(source,'src'),path.join(scratch,'src'),{recursive:true});
fs.writeFileSync(path.join(scratch,'src/labActivity.ts'),`
import * as fs from 'fs';import * as os from 'os';import * as path from 'path';
let last=0;let busy=false;
export function touch(){if(Date.now()-last<2000)return;last=Date.now();try{const dir=path.join(os.homedir(),'.config/lab');fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,'activity.json'),JSON.stringify({at:Date.now()/1000}),{mode:0o600});}catch{}}
export function setBusy(value:boolean){busy=value;touch();}
const timer=setInterval(()=>{if(busy)touch();},15000);timer.unref();
`);
let extension=fs.readFileSync(path.join(scratch,'src/extension.ts'),'utf8');
extension=extension.replace('runInstall(context);',"vscode.window.showInformationMessage('Pi and Ori are preinstalled. Package access is managed by Sandbox Lab.');");
extension=extension.replaceAll('runInstall(context);',"vscode.window.showInformationMessage('Extensions and MCP servers require an approved lab policy.');");
extension=extension.replace('runDependencyCheck(context);',"vscode.window.showInformationMessage('Pi/Ori is preloaded. Refresh model access in Sandbox Lab, then reload this window.');");
extension=extension.replace("console.log('[pi-chat] activating...');","console.log('[pi-chat] activating...'); setTimeout(()=>vscode.commands.executeCommand('piChat.sidebar.focus'),1500);");
extension=extension.replace("const pick = await vscode.window.showQuickPick(","vscode.window.showInformationMessage('Model access is managed by Sandbox Lab. Use Refresh Ori / Pi there, then reload this window.'); return; const pick = await vscode.window.showQuickPick(");
extension="import {touch} from './labActivity';\n"+extension;
extension=extension.replace("console.log('[pi-chat] activating...');", "console.log('[pi-chat] activating...'); touch(); context.subscriptions.push(vscode.workspace.onDidChangeTextDocument(touch),vscode.window.onDidChangeTextEditorSelection(touch),vscode.window.onDidChangeActiveTextEditor(touch),vscode.window.onDidStartTerminalShellExecution(touch));");
fs.writeFileSync(path.join(scratch,'src/extension.ts'),extension);
let sidebar=fs.readFileSync(path.join(scratch,'src/chatSidebarProvider.ts'),'utf8').replace('data: https:;','data:;');
sidebar="import {touch,setBusy} from './labActivity';\n"+sidebar;
sidebar=sidebar.replace("case 'agent_start':","case 'agent_start': setBusy(true);").replace("case 'agent_end':","case 'agent_end': setBusy(false);").replace("case 'prompt':","case 'prompt': touch();");
fs.writeFileSync(path.join(scratch,'src/chatSidebarProvider.ts'),sidebar);
let rpc=fs.readFileSync(path.join(scratch,'src/piRpcClient.ts'),'utf8');
rpc=rpc.replace("console.warn('[pi stderr]', text);",'// Model/provider notices remain in the workspace, not the browser console.');
rpc="import {setBusy} from './labActivity';\n"+rpc;
rpc=rpc.replaceAll('this._isRunning = false;', 'this._isRunning = false; setBusy(false);');
fs.writeFileSync(path.join(scratch,'src/piRpcClient.ts'),rpc);
await build({entryPoints:[path.join(scratch,'src/extension.ts')],outfile:path.join(out,'out/extension.js'),platform:'node',format:'cjs',bundle:true,external:['vscode'],minify:true});
const vendor=fs.readFileSync(path.join(source,'media/vendor-entry.js'),'utf8')+'\nimport DOMPurify from "dompurify"; window.DOMPurify=DOMPurify;';
await build({stdin:{contents:vendor,resolveDir:path.join(root,'.local/vendor/pi-chat-build'),loader:'js'},outfile:path.join(out,'media/vendor.js'),bundle:true,format:'iife',minify:true});
let ui=fs.readFileSync(path.join(source,'media/main.js'),'utf8').replace('window.marked.parse(text)','window.DOMPurify.sanitize(window.marked.parse(text))');
fs.writeFileSync(path.join(out,'media/main.js'),ui);
for(const f of ['style.css','vendor.css'])fs.copyFileSync(path.join(source,'media',f),path.join(out,'media',f));
for(const f of ['package.json','LICENSE','icon.png'])fs.copyFileSync(path.join(source,f),path.join(out,f));
const manifest=JSON.parse(fs.readFileSync(path.join(out,'package.json'),'utf8'));manifest.activationEvents=['onStartupFinished'];manifest.contributes.viewsContainers.secondarySidebar=manifest.contributes.viewsContainers.activitybar;delete manifest.contributes.viewsContainers.activitybar;fs.writeFileSync(path.join(out,'package.json'),JSON.stringify(manifest,null,2));
fs.writeFileSync(path.join(out,'UPSTREAM.md'),`Source: https://github.com/iqbalabiyoga/pi-vscode-chat\nCommit: ${commit}\nLicense: MIT (included)\nLocal patches: sanitize Markdown, remove remote webview images, disable unmanaged install/auth wizards, configure the executable externally as ori-lab; default to the secondary sidebar; report edit/terminal/Pi activity for idle shutdown. The upstream UI is retained.\nBuild: scripts/build_pi_chat.mjs\n`);
execFileSync(path.join(root,'.venv/bin/python'),[path.join(root,'scripts/patch_pi_dictation.py')]);
execFileSync(path.join(root,'.venv/bin/python'),[path.join(root,'scripts/package_pi_chat.py')]);
