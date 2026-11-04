import json
import shutil
import subprocess
import pytest
from backend.public_preview import render


@pytest.mark.skipif(not shutil.which('node'),reason='Node is required for browser-shell regression test')
def test_shared_preview_shell_runs_without_secure_context_crypto():
    page=render('<h1>HTTP preview</h1>','namespace')
    script=page.split('<script>',1)[1].rsplit('</script>',1)[0]
    check=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const source=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const frame={contentWindow:{}},events={};
const store={getItem:()=>null,setItem(){}};
// No crypto or randomUUID, as on a plain-HTTP page.
vm.runInNewContext(source,{document:{querySelector:()=>frame},localStorage:store,sessionStorage:store,addEventListener:(name,fn)=>events[name]=fn});
assert.ok(frame.srcdoc.includes('<h1>HTTP preview</h1>'));
const window={};
for(const key of ['localStorage','sessionStorage'])Object.defineProperty(window,key,{configurable:true,get(){throw Error('SecurityError')}});
vm.runInNewContext(frame.srcdoc.split('<script>')[1].split('</script>')[0],{window,parent:{postMessage(){}},addEventListener(){}});
window.sessionStorage.setItem('key','value');assert.equal(window.sessionStorage.getItem('key'),'value');
'''
    result=subprocess.run(['node','-e',check],input=json.dumps(script),text=True,capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr
