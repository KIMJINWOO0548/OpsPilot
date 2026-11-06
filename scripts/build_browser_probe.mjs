// Uses existing dependency tree read-only; writes isolated .local/browser-dist only.
import path from 'node:path';import {pathToFileURL} from 'node:url';
const deps=process.env.OPS_WEB_DEPS;if(!deps)throw new Error('OPS_WEB_DEPS required');
const {build}=await import(pathToFileURL(path.join(deps,'vite/dist/node/index.js')));
const root=path.resolve(import.meta.dirname,'..');
await build({configFile:false,root:path.join(root,'web'),resolve:{alias:[{find:/^react-dom(\/.*)?$/,replacement:path.join(deps,'react-dom')+'$1'},{find:/^react(\/.*)?$/,replacement:path.join(deps,'react')+'$1'}]},build:{outDir:path.join(root,'.local/browser-dist'),emptyOutDir:false}});
