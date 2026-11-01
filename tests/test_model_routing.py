import json
import httpx
import pytest
from backend.agents import model


@pytest.fixture
def requests(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-deepseek-key')
    monkeypatch.setenv('DASHSCOPE_API_KEY','test-dashscope-key')
    monkeypatch.setenv('DEEPSEEK_BASE_URL','https://api.deepseek.com')
    monkeypatch.setenv('DASHSCOPE_BASE_URL','https://dashscope.aliyuncs.com')
    monkeypatch.setenv('CODE_MODEL','deepseek-flash')
    monkeypatch.setenv('TEXT_MODEL','text-model')
    monkeypatch.setenv('VISION_MODEL','vision-model')
    captured=[]
    def handle(request):
        captured.append(request)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"html":"<html></html>"}'}}]})
    client=httpx.AsyncClient
    monkeypatch.setattr(model.httpx,'AsyncClient',lambda **kwargs:client(transport=httpx.MockTransport(handle),**kwargs))
    return captured


@pytest.mark.asyncio
async def test_code_uses_deepseek_and_preserves_reference_image(requests):
    reference='data:image/png;base64,fixture'
    result=await model.ask('test','只输出JSON','生成网页',coding=True,images=[reference])
    request=requests[0];payload=json.loads(request.content)
    assert str(request.url)=='https://api.deepseek.com/chat/completions'
    assert request.headers['Authorization']=='Bearer test-deepseek-key'
    assert payload['model']=='deepseek-flash'
    assert payload['thinking']=={'type':'disabled'}
    assert 'enable_thinking' not in payload
    assert payload['messages'][1]['content'][1]['image_url']['url']==reference
    assert result['html']=='<html></html>'


@pytest.mark.asyncio
@pytest.mark.parametrize('vision,expected',[(False,'text-model'),(True,'vision-model')])
async def test_non_code_calls_stay_on_dashscope(requests,vision,expected):
    await model.ask('test','JSON','需求分析',vision=vision)
    request=requests[0];payload=json.loads(request.content)
    assert str(request.url)=='https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
    assert request.headers['Authorization']=='Bearer test-dashscope-key'
    assert payload['model']==expected
    assert payload['enable_thinking'] is False and 'thinking' not in payload


@pytest.mark.asyncio
async def test_missing_deepseek_key_never_falls_back_to_dashscope(requests,monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY')
    with pytest.raises(model.ModelError,match='未配置 DEEPSEEK_API_KEY'):
        await model.ask('test','JSON','code',coding=True)
    assert not requests


@pytest.mark.asyncio
async def test_versioned_deepseek_base_url(requests,monkeypatch):
    monkeypatch.setenv('DEEPSEEK_BASE_URL','https://api.deepseek.com/v1/')
    await model.ask('test','JSON','code',coding=True)
    assert str(requests[0].url)=='https://api.deepseek.com/v1/chat/completions'


@pytest.mark.asyncio
async def test_text_only_code_model_cannot_silently_drop_reference(requests,monkeypatch):
    monkeypatch.setenv('CODE_MODEL','deepseek-v4-pro')
    with pytest.raises(model.ModelError,match='支持图片输入'):
        await model.ask('test','JSON','code',coding=True,images=['data:image/png;base64,fixture'])
    assert not requests


@pytest.mark.asyncio
async def test_health_reports_code_key_independently(requests,monkeypatch):
    from backend.main import health
    monkeypatch.delenv('DEEPSEEK_API_KEY')
    result=await health()
    assert result['configured'] is False and result['design_configured'] is True
    assert result['model']=='deepseek-flash'
