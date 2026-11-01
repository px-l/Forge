import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const input=fs.readFileSync(new URL('../src/browser.ts',import.meta.url),'utf8');
const js=ts.transpileModule(input,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {createPreviewToken,copyText}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
test('HTTP crypto without randomUUID generates a 256-bit preview token',()=>{
 let size=0;
 const source={getRandomValues:bytes=>{size=bytes.length;return bytes.fill(0xab);}};
 assert.equal(createPreviewToken(source),'ab'.repeat(32));
 assert.equal(size,32);
});
test('secure preview tokens differ and do not fall back to Math.random',()=>{
 assert.match(createPreviewToken(),/^[a-f0-9]{64}$/);
 assert.notEqual(createPreviewToken(),createPreviewToken());
 assert.throws(()=>createPreviewToken({}),/安全随机数/);
});
test('HTTP clipboard fallback copies and restores focus',async()=>{
 const nav=Object.getOwnPropertyDescriptor(globalThis,'navigator');
 const doc=Object.getOwnPropertyDescriptor(globalThis,'document');
 let removed=false,focused=false,selected=false,copied=false;
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{}});
 Object.defineProperty(globalThis,'document',{configurable:true,value:{
   activeElement:{focus:()=>{focused=true;}},getSelection:()=>null,
   createElement:()=>({value:'',style:{},setAttribute(){},focus(){},select(){selected=true;},remove(){removed=true;}}),
   body:{append(){}},execCommand:command=>{copied=command==='copy';return copied;}
 }});
 try{assert.equal(await copyText('http://example.test/p/token'),true);assert.ok(removed&&focused&&selected&&copied);}
 finally{if(nav)Object.defineProperty(globalThis,'navigator',nav);else delete globalThis.navigator;if(doc)Object.defineProperty(globalThis,'document',doc);else delete globalThis.document;}
});
