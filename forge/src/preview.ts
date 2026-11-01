export function previewDocument(
  html: string,
  token: string,
  data: Record<string, string>,
  sessionData: Record<string, string> = {},
) {
  const serialize = (value: Record<string,string>) => JSON.stringify(value).replace(/</g, "\\u003c");
  const bridge = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"><script>(function(){const token=${JSON.stringify(token)};function send(type,payload){parent.postMessage({forge:token,type,...payload},'*')}function storage(seed,area){let values=Object.assign(Object.create(null),seed);return {getItem:k=>values[String(k)]??null,setItem:(k,v)=>{values[String(k)]=String(v);send('storage',{area,data:values})},removeItem:k=>{delete values[String(k)];send('storage',{area,data:values})},clear:()=>{values=Object.create(null);send('storage',{area,data:values})},key:i=>Object.keys(values)[Number(i)]??null,get length(){return Object.keys(values).length}}}Object.defineProperty(window,'localStorage',{value:storage(${serialize(data)},'local')});Object.defineProperty(window,'sessionStorage',{value:storage(${serialize(sessionData)},'session')});addEventListener('error',e=>send('error',{error:e.message}));addEventListener('unhandledrejection',e=>send('error',{error:String(e.reason)}));})();</script>`;
  return '<!doctype html><html><head>'+bridge+'</head><body>'+html.replace(/<!doctype[^>]*>/gi,'')+'</body></html>';
}
