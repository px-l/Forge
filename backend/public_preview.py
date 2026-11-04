"""Read-only shared application shell; generated scripts run in an opaque iframe."""
import json
import secrets


def render(html: str, namespace: str) -> str:
    encoded = json.dumps(html, ensure_ascii=False).replace('<', '\\u003c')
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>网站预览</title><style>html,body,iframe{margin:0;width:100%;height:100%;border:0;display:block}</style></head><body><iframe title="网站预览" sandbox="allow-scripts allow-forms"></iframe><script>
const frame=document.querySelector('iframe'), key='forge-shared-''' + namespace + '''',token=''' + json.dumps(secrets.token_urlsafe(32)) + ''';
let local={},session={};try{local=JSON.parse(localStorage.getItem(key)||'{}')}catch{}try{session=JSON.parse(sessionStorage.getItem(key)||'{}')}catch{}
function storageBridge(localSeed,sessionSeed,token){
function storage(seed,area){let values=Object.assign(Object.create(null),seed);function save(){parent.postMessage({token,area,data:values},'*')}return {getItem:k=>values[String(k)]??null,setItem:(k,v)=>{values[String(k)]=String(v);save()},removeItem:k=>{delete values[String(k)];save()},clear:()=>{values=Object.create(null);save()},key:i=>Object.keys(values)[Number(i)]??null,get length(){return Object.keys(values).length}}}
addEventListener('click',e=>{
const link=e.target instanceof Element && e.target.closest('a[href^="#/"]');
if(link){e.preventDefault();location.hash=link.getAttribute('href')}
},true);
Object.defineProperty(window,'localStorage',{value:storage(localSeed,'local')});Object.defineProperty(window,'sessionStorage',{value:storage(sessionSeed,'session')});
}
const safe=v=>JSON.stringify(v).replace(/</g,'\\\\u003c');
const bridge='<script>('+storageBridge.toString()+')('+safe(local)+','+safe(session)+','+safe(token)+');<'+ '/script>';
addEventListener('message',e=>{if(e.source!==frame.contentWindow||e.data?.token!==token)return;const raw=JSON.stringify(e.data.data);if(raw.length<=2000000)try{(e.data.area==='session'?sessionStorage:localStorage).setItem(key,raw)}catch{}});
frame.srcdoc=bridge+''' + encoded + ''';
</script></body></html>'''
