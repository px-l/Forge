import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source=fs.readFileSync(new URL('../src/preview.ts',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {previewDocument}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
function sandbox(local={},session={}){
 const messages=[],window={};
 for(const name of ['localStorage','sessionStorage'])Object.defineProperty(window,name,{configurable:true,get(){throw Error('SecurityError')}});
 const context={window,parent:{postMessage:m=>messages.push(m)},addEventListener:()=>{}};
 const html=previewDocument('<h1>preview</h1>','token',local,session);
 vm.runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
 return {window,messages,html};
}
test('sandboxed sessionStorage is readable and independent of localStorage',()=>{
 const {window:w,messages}=sandbox({saved:'local'},{saved:'session'});
 assert.equal(w.sessionStorage.getItem('saved'),'session');
 w.sessionStorage.setItem('saved',42);
 assert.equal(w.localStorage.getItem('saved'),'local');
 assert.equal(w.sessionStorage.getItem('saved'),'42');
 assert.equal(messages.at(-1).area,'session');
 w.sessionStorage.removeItem('saved');assert.equal(w.sessionStorage.length,0);
 w.sessionStorage.setItem('x','y');assert.equal(w.sessionStorage.key(0),'x');
 w.sessionStorage.clear();assert.equal(w.sessionStorage.getItem('x'),null);
});
test('session seed restores on preview reload without exposing injected markup',()=>{
 const value='</script><script>bad()</script>';
 const a=sandbox({},{});a.window.sessionStorage.setItem('value',value);
 const b=sandbox({},a.messages.at(-1).data);
 assert.equal(b.window.sessionStorage.getItem('value'),value);
 assert.equal(b.html.includes('<script>bad()'),false);
});
