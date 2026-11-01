import json
import pytest
from backend import store
from backend.design_spec import normalize,constrain,repair_instructions
from backend.agents import nodes


def test_spec_bounds_and_module_identity():
    assert normalize({})['hero_layout']=='two-columns'
    with pytest.raises(ValueError):normalize({'heading_size':150})
    with pytest.raises(ValueError):normalize({'accent':'red;display:none'})
    with pytest.raises(ValueError):normalize({'sections':[{'id':'hero','label':'one'},{'id':'hero','label':'two'}]})


def test_contract_locks_desktop_and_keeps_behavior():
    code='<html><head></head><body><script>function jump(){return 42}</script></body></html>'
    spec=normalize({})
    result=constrain(code,spec)
    assert 'grid-template-columns:minmax(0,36fr) minmax(0,64fr)!important' in result
    assert 'font-size:48px!important' in result
    assert 'max-width:900px' in result
    assert 'function jump(){return 42}' in result
    assert constrain(result,spec).count('id="forge-design-contract"')==1


@pytest.mark.asyncio
async def test_static_layout_precedes_function_generation(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DB',tmp_path/'db');store.init()
    calls=[]
    async def ask(tid,system,prompt,**kw):
        calls.append(json.loads(prompt))
        if len(calls)==1:return {'html':'<html><head></head><body data-layout="fixed"></body></html>'}
        return {'html':'<html><head></head><body data-layout="fixed"><button>开始</button></body></html>','summary':'done'}
    monkeypatch.setattr(nodes,'ask',ask)
    r=await nodes.develop({'task_id':'test','prompt':'跑酷小游戏','demo':False,'requirements':{},'design_spec':normalize({}),'repairs':0})
    assert len(calls)==2
    assert 'data-layout="fixed"' in calls[1]['current_html']
    assert calls[1]['design_spec']['heading_size']==48
    assert 'forge-design-contract' in r['html']
    assert store.get_artifact(r['code_id'])['content']['design_spec']['hero_layout']=='two-columns'


def test_repair_locks_unaffected_work():
    value=repair_instructions({'feedback':{'layout':{'passed':False,'issues':[{'area':'hero','issue':'missing'}]}}})
    assert '布局' in value['focus']
    assert '现有功能与存储key' in value['preserve']

@pytest.mark.asyncio
async def test_image_and_code_receive_same_spec(tmp_path,monkeypatch):
    from backend.sample import SAMPLE_TARGET
    monkeypatch.setattr(store,'DB',tmp_path/'db');store.init()
    async def ask(*args,**kwargs):return {'hero_left_percent':40,'heading_size':42}
    captured={}
    async def image(tid,prompt):captured.update(json.loads(prompt));return SAMPLE_TARGET
    monkeypatch.setattr(nodes,'ask',ask);monkeypatch.setattr(nodes,'image',image)
    r=await nodes.design({'task_id':'test','demo':False,'requirements':{'summary':'test'},'requirement_id':'req'})
    assert captured['design_spec']['hero_left_percent']==r['design_spec']['hero_left_percent']==40
    assert captured['design_spec']['heading_size']==r['design_spec']['heading_size']==42
    # If provider returns a different size, honor actual reference dimensions.
    assert r['design_spec']['width']==1440


@pytest.mark.asyncio
async def test_capture_url_accepts_query_and_keeps_token_protection():
    import httpx
    from backend.uiproof import preview_server
    async with preview_server('<html>capture fixture</html>') as (port,token):
        async with httpx.AsyncClient() as client:
            valid=await client.get(f'http://127.0.0.1:{port}/{token}?forge_capture=1')
            invalid=await client.get(f'http://127.0.0.1:{port}/wrong?forge_capture=1')
    assert valid.status_code==200 and 'capture fixture' in valid.text
    assert invalid.status_code==404
