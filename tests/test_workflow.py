import asyncio
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from backend import store, workflow
from backend.sample import SAMPLE_HTML, SAMPLE_TARGET


@pytest.fixture(autouse=True)
def temporary_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "test.db")
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.init()


def state(**kwargs):
    return {
        "task_id": store.uid(),
        "project_id": "test",
        "prompt": "创建待办应用",
        "mode": "new",
        "demo": True,
        "wants_design": True,
        "repairs": 0,
        **kwargs,
    }


@pytest.mark.asyncio
async def test_design_confirmation_and_delivery(monkeypatch):
    async def validation(s):
        return {"passed": True, "report_id": "report", "feedback": {}}

    monkeypatch.setattr(workflow, "validate", validation)
    g = workflow.build(InMemorySaver())
    cfg = {"configurable": {"thread_id": "one"}}
    r = await g.ainvoke(state(), cfg)
    assert r["__interrupt__"][0].value["node"] == "design"
    assert "html" not in r
    r = await g.ainvoke(Command(resume={"approved": True}), cfg)
    assert r["passed"] and r["code_id"] and r["requirement_id"] and r["design_id"]
    with store.conn() as c:
        assert (
            c.execute(
                "SELECT COUNT(*) FROM artifacts WHERE kind='delivery'"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.asyncio
async def test_repair_limit(monkeypatch):
    calls = []

    async def fail(s):
        calls.append(s["repairs"])
        return {"passed": False, "feedback": {"errors": ["overflow"]}}

    monkeypatch.setattr(workflow, "validate", fail)
    g = workflow.build(InMemorySaver())
    r = await g.ainvoke(
        state(wants_design=False), {"configurable": {"thread_id": "repair"}}
    )
    assert calls == [1, 2, 3] and r["repairs"] == 3 and not r["passed"]
    assert r["generation_stopped"] and "__interrupt__" not in r


@pytest.mark.asyncio
async def test_prototype_does_not_develop():
    g = workflow.build(InMemorySaver())
    r = await g.ainvoke(
        state(mode="prototype"), {"configurable": {"thread_id": "prototype"}}
    )
    assert r["design_id"] and "html" not in r


@pytest.mark.asyncio
async def test_modify_skips_design(monkeypatch):
    async def passed(s):
        return {"passed": True, "feedback": {}}

    monkeypatch.setattr(workflow, "validate", passed)
    r = await workflow.build(InMemorySaver()).ainvoke(
        state(mode="modify", html=SAMPLE_HTML),
        {"configurable": {"thread_id": "modify"}},
    )
    assert r["code_id"] and "design_id" not in r


@pytest.mark.asyncio
async def test_api_ownership_and_sse(monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    async def passed(s):
        return {"passed": True, "feedback": {}}

    monkeypatch.setattr(workflow, "validate", passed)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/api/projects",
                json={"prompt": "待办应用", "demo": True, "wants_design": True},
            )
            assert r.status_code == 200
            pid, tid = r.json()["project_id"], r.json()["task_id"]
            for _ in range(100):
                p = (await client.get("/api/projects/" + pid)).json()
                if p["tasks"][-1]["status"] == "needs_input":
                    break
                await asyncio.sleep(0.02)
            assert p["tasks"][-1]["status"] == "needs_input"
            duplicate = await client.post(
                "/api/projects/" + pid + "/tasks",
                json={"prompt": "另一个任务", "demo": True},
            )
            assert duplicate.status_code == 409
            assert (
                await client.post(
                    "/api/tasks/" + tid + "/resume", json={"answer": {"approved": True}}
                )
            ).status_code == 200
            for _ in range(100):
                p = (await client.get("/api/projects/" + pid)).json()
                if p["tasks"][-1]["status"] == "completed":
                    break
                await asyncio.sleep(0.02)
            assert p["tasks"][-1]["status"] == "completed"
            stream = await client.get("/api/tasks/" + tid + "/events")
            assert "event: settled" in stream.text and "artifact" in stream.text
            code = next(a for a in p["artifacts"] if a["kind"] == "code")
            assert (
                "sandbox"
                in (
                    await client.get("/api/artifacts/" + code["id"] + "/preview")
                ).headers["content-security-policy"]
            )
            assert (
                await client.get("/api/artifacts/" + code["id"] + "/download")
            ).status_code == 200
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as stranger:
                assert (await stranger.get("/api/projects/" + pid)).status_code == 404
                assert (
                    await stranger.get("/api/artifacts/" + code["id"] + "/preview")
                ).status_code == 404


@pytest.mark.asyncio
async def test_missing_key_fails_honestly(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    from backend.agents.model import ask, ModelError

    with pytest.raises(ModelError, match="未配置"):
        await ask("test", "test", "test")


@pytest.mark.asyncio
async def test_sqlite_pause_survives_restart(tmp_path, monkeypatch):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    async def passed(s):
        return {"passed": True, "feedback": {}}

    monkeypatch.setattr(workflow, "validate", passed)
    cfg = {"configurable": {"thread_id": "durable"}}
    db = str(tmp_path / "graph.db")
    async with AsyncSqliteSaver.from_conn_string(db) as cp:
        r = await workflow.build(cp).ainvoke(state(), cfg)
        assert r["__interrupt__"]
    async with AsyncSqliteSaver.from_conn_string(db) as cp:
        r = await workflow.build(cp).ainvoke(Command(resume={"approved": True}), cfg)
        assert r["passed"] and r["code_id"]


@pytest.mark.asyncio
async def test_requirements_clarification(monkeypatch):
    async def unclear(s):
        return {
            "requirements": {"summary": "开发应用", "questions": ["主要用户是谁？"]},
            "requirement_id": "old",
        }

    async def passed(s):
        return {"passed": True, "feedback": {}}

    monkeypatch.setattr(workflow.nodes, "clarify", unclear)
    monkeypatch.setattr(workflow, "validate", passed)
    g = workflow.build(InMemorySaver())
    cfg = {"configurable": {"thread_id": "clarification"}}
    r = await g.ainvoke(state(wants_design=False), cfg)
    assert r["__interrupt__"][0].value["node"] == "clarify"
    r = await g.ainvoke(Command(resume="小型研发团队"), cfg)
    assert r["requirements"]["clarification"] == "小型研发团队"
    assert r["requirement_id"] != "old" and r["passed"]


@pytest.mark.asyncio
async def test_restore_persists_and_is_project_scoped(monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    async def passed(s):
        return {"passed": True, "feedback": {}}

    monkeypatch.setattr(workflow, "validate", passed)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def build_project():
                r = (
                    await client.post(
                        "/api/projects", json={"prompt": "创建待办应用", "demo": True}
                    )
                ).json()
                for _ in range(100):
                    p = (await client.get("/api/projects/" + r["project_id"])).json()
                    if p["tasks"][-1]["status"] == "completed":
                        return p
                    await asyncio.sleep(0.02)
                raise AssertionError("task did not complete")

            p = await build_project()
            other = await build_project()
            code = next(a for a in p["artifacts"] if a["kind"] == "code")
            assert (
                await client.post(
                    "/api/projects/" + other["id"] + "/restore",
                    json={"code_id": code["id"]},
                )
            ).status_code == 400
            assert (
                await client.post(
                    "/api/projects/" + p["id"] + "/restore",
                    json={"code_id": code["id"]},
                )
            ).status_code == 200
            restored = (await client.get("/api/projects/" + p["id"])).json()
            assert restored["current_code_id"] == code["id"]

@pytest.mark.asyncio
async def test_uiproof_gate_and_report_artifact(monkeypatch):
    import httpx
    original_client = httpx.AsyncClient
    def response(request):
        return httpx.Response(200,json={'passed':True,'checks':{'has_content':True},'interactions':[]})
    monkeypatch.setattr(workflow.httpx,'AsyncClient',lambda **kw: original_client(transport=httpx.MockTransport(response),**kw))
    monkeypatch.setenv('VISUAL_VALIDATOR','uiproof')
    async def proof(s):
        return {'provider':'uiproof','passed':False,'run_id':'test-run','context':{},'states':[],'issues':[],'report_html':'<html>evidence</html>'}
    monkeypatch.setattr(workflow.uiproof,'verify',proof)
    r=await workflow.validate(state(html=SAMPLE_HTML,code_id='code',target=SAMPLE_TARGET,design_id='design'))
    assert not r['passed']
    aid=r['feedback']['uiproof']['report_artifact_id']
    assert store.get_artifact(aid)['content']['code_id']=='code'

@pytest.mark.asyncio
async def test_uiproof_transport_error_is_not_a_visual_failure(monkeypatch):
    import httpx
    original_client=httpx.AsyncClient
    monkeypatch.setattr(workflow.httpx,'AsyncClient',lambda **kw:original_client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'passed':True})),**kw))
    monkeypatch.setenv('VISUAL_VALIDATOR','uiproof')
    async def unavailable(s):raise workflow.uiproof.UIProofError('connection failed')
    monkeypatch.setattr(workflow.uiproof,'verify',unavailable)
    with pytest.raises(workflow.uiproof.UIProofError):
        await workflow.validate(state(html=SAMPLE_HTML,code_id='code',target=SAMPLE_TARGET,design_id='design'))

@pytest.mark.asyncio
async def test_code_tree_is_actual_reproducible_git_tree():
    from backend.uiproof import code_tree
    first=await code_tree('<h1>hello</h1>')
    assert first==await code_tree('<h1>hello</h1>')
    assert first!=await code_tree('<h1>changed</h1>')
    assert len(first)==40

@pytest.mark.parametrize('ratio,expected',[(0.09,'review_gate'),(0.10,'review_gate'),(0.10001,'develop'),(0.4,'develop')])
def test_visual_threshold_routes(ratio,expected):
    assert workflow.repair_gate({'passed':False,'repairs':1,'feedback':{'browser_passed':True,'uiproof':{'states':[{'ratio':ratio}]}}})==expected

@pytest.mark.asyncio
async def test_small_difference_can_be_accepted(monkeypatch):
    async def small(s):return {'passed':False,'feedback':{'browser_passed':True,'uiproof':{'states':[{'ratio':.08}]}}}
    monkeypatch.setattr(workflow,'validate',small)
    g=workflow.build(InMemorySaver());cfg={'configurable':{'thread_id':'small-diff'}}
    r=await g.ainvoke(state(wants_design=False),cfg)
    assert r['__interrupt__'][0].value['node']=='review'
    assert r['repairs']==1
    r=await g.ainvoke(Command(resume={'regenerate':False}),cfg)
    assert r['user_accepted'] and not r['passed']
    assert '__interrupt__' not in r

@pytest.mark.asyncio
async def test_large_difference_stops_after_three_generations(monkeypatch):
    async def large(s):return {'passed':False,'feedback':{'browser_passed':True,'uiproof':{'states':[{'ratio':.3}]}}}
    monkeypatch.setattr(workflow,'validate',large)
    g=workflow.build(InMemorySaver());cfg={'configurable':{'thread_id':'large-diff'}}
    r=await g.ainvoke(state(wants_design=False),cfg)
    assert r['repairs']==3 and r['generation_stopped']
    assert '__interrupt__' not in r
    with store.conn() as c:
        assert c.execute("SELECT count(*) FROM artifacts WHERE kind='delivery'").fetchone()[0]==0
        errors=[__import__('json').loads(row[0]) for row in c.execute("SELECT payload FROM events WHERE task_id=?",(r['task_id'],))]
    assert [e['message'] for e in errors if e['type']=='error']==[workflow.GENERATION_FAILURE_MESSAGE]

@pytest.mark.asyncio
async def test_share_link_works_without_owner_cookie(monkeypatch):
    from httpx import AsyncClient,ASGITransport
    from backend.main import app
    async def passed(s):return {'passed':True,'feedback':{}}
    monkeypatch.setattr(workflow,'validate',passed)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as owner:
            created=(await owner.post('/api/projects',json={'prompt':'创建待办应用','demo':True})).json()
            for _ in range(100):
                p=(await owner.get('/api/projects/'+created['project_id'])).json()
                if p['tasks'][-1]['status']=='completed':break
                await asyncio.sleep(.02)
            code=next(a for a in p['artifacts'] if a['kind']=='code')
            link=(await owner.post('/api/artifacts/'+code['id']+'/share',json={})).json()['url']
            async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as other:
                shared=await other.get(link)
                assert shared.status_code==200 and 'sandbox="allow-scripts allow-forms"' in shared.text
                assert '任务工作台' in shared.text
                assert (await other.get('/api/projects/'+p['id'])).status_code==404
                assert (await other.get('/p/incorrect-token')).status_code==404
                assert (await other.post('/api/artifacts/'+code['id']+'/share',json={})).status_code==404

@pytest.mark.asyncio
async def test_memory_survives_two_modification_rounds(monkeypatch):
    import json
    from httpx import AsyncClient,ASGITransport
    from backend.main import app
    async def passed(s):return {'passed':True,'feedback':{}}
    monkeypatch.setattr(workflow,'validate',passed)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            created=(await client.post('/api/projects',json={'prompt':'原始目标：研发工作台','demo':True})).json()
            pid=created['project_id']
            async def finished():
                for _ in range(100):
                    p=(await client.get('/api/projects/'+pid)).json()
                    if p['tasks'][-1]['status']=='completed':return p
                    await asyncio.sleep(.02)
                raise AssertionError('task unfinished')
            p=await finished()
            saved=await client.post('/api/projects/'+pid+'/memory',json={**p['memory'],'design_constraints':['保持深色主题'],'protected_items':['保留存储结构']})
            assert saved.status_code==200
            rev=saved.json()['revision']
            assert (await client.post('/api/projects/'+pid+'/memory',json={**p['memory'],'goal':'stale edit'})).status_code==409
            for request in ['增加搜索功能','增加任务优先级']:
                base=p['current_code_id']
                r=await client.post('/api/projects/'+pid+'/tasks',json={'prompt':request,'mode':'modify','demo':True,'base_code_id':base})
                assert r.status_code==200
                p=await finished()
                payload=json.loads(p['tasks'][-1]['payload'])
                assert payload['memory']['goal']=='原始目标：研发工作台'
                assert payload['memory']['protected_items']==['保留存储结构']
                assert payload['memory']['design_constraints']==['保持深色主题']
                assert payload['memory']['revision']>=rev
                assert '新增与完成任务' in p['memory']['features']
            assert [x['request'] for x in p['memory']['changes']][-2:]==['增加搜索功能','增加任务优先级']
            assert p['memory']['goal']=='原始目标：研发工作台'
            assert p['memory']['protected_items']==['保留存储结构']
            async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as other:
                assert (await other.post('/api/projects/'+pid+'/memory',json={**p['memory']})).status_code==404

@pytest.mark.asyncio
async def test_developer_receives_memory_and_prior_requests(monkeypatch):
    import json
    from backend.agents import nodes
    captured={}
    async def model(tid,system,prompt,**kw):
        captured.update({'system':system,'prompt':json.loads(prompt)})
        return {'html':'<html><body>updated</body></html>','summary':'done','tests':[],'requirements_update':{'features':['原有功能','新增搜索']}}
    monkeypatch.setattr(nodes,'ask',model)
    r=await nodes.develop(state(demo=False,html='<p>old</p>',requirements={'summary':'原始说明'},memory={'revision':3,'goal':'原始目标','features':['原有功能'],'protected_items':['保留支付入口'],'design_constraints':['深色'],'changes':[{'task_id':'older','request':'上一轮增加筛选'}]},memory_id='snapshot'))
    assert captured['prompt']['project_memory']['protected_items']==['保留支付入口']
    assert captured['prompt']['project_memory']['changes'][0]['request']=='上一轮增加筛选'
    assert captured['prompt']['current_html']=='<p>old</p>'
    assert r['requirements']['summary']=='原始说明'
    assert r['requirements']['features']==['原有功能','新增搜索']
    assert store.get_artifact(r['code_id'])['content']['memory_id']=='snapshot'

@pytest.mark.asyncio
async def test_permanent_delete_revokes_preview_and_removes_project_data(monkeypatch):
    from httpx import AsyncClient,ASGITransport
    from backend.main import app
    async def passed(s):return {'passed':True,'feedback':{}}
    monkeypatch.setattr(workflow,'validate',passed)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
            result=(await c.post('/api/projects',json={'prompt':'删除功能测试','demo':True})).json();pid=result['project_id']
            for _ in range(100):
                project=(await c.get('/api/projects/'+pid)).json()
                if project['tasks'][-1]['status']=='completed':break
                await asyncio.sleep(.02)
            code=project['current_code_id']
            url=(await c.post('/api/artifacts/'+code+'/share',json={})).json()['url']
            async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as other:
                assert (await other.post('/api/projects/'+pid+'/delete',json={})).status_code==404
                assert (await other.get(url)).status_code==200
                assert (await c.post('/api/projects/'+pid+'/delete',json={})).status_code==200
                assert all(p['id']!=pid for p in (await c.get('/api/projects')).json())
                assert (await c.get('/api/projects/'+pid)).status_code==404
                assert (await c.get('/api/artifacts/'+code+'/download')).status_code==404
                assert (await c.post('/api/projects/'+pid+'/tasks',json={'prompt':'不能继续修改','demo':True})).status_code==404
                assert (await other.get(url)).status_code==404
                assert (await other.post('/api/projects/'+pid+'/undelete',json={})).status_code in (404,405)
                assert (await c.post('/api/projects/'+pid+'/undelete',json={})).status_code in (404,405)
                with store.conn() as db:
                    for table in ('projects','tasks','artifacts','events','project_memory','memory_versions','preview_links'):
                        assert db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
                snapshot=await app.state.graph.aget_state({'configurable':{'thread_id':result['task_id']}})
                assert not snapshot.values

@pytest.mark.asyncio
async def test_active_project_cannot_be_deleted():
    from httpx import AsyncClient,ASGITransport
    from backend.main import app
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
            await c.get('/api/health')
            pid,tid=store.uid(),store.uid()
            with store.conn() as db:
                db.execute('INSERT INTO projects(id,owner,name,created) VALUES(?,?,?,?)',(pid,c.cookies.get('forge_visitor'),'active',store.now()))
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?)',(tid,pid,'running','{"prompt":"active"}',store.now()))
            assert (await c.post('/api/projects/'+pid+'/delete',json={})).status_code==409
            assert (await c.get('/api/projects/'+pid)).status_code==200


@pytest.mark.asyncio
@pytest.mark.parametrize('third_passed,expected',[(True,'deliver'),(False,'review_gate')])
async def test_third_generation_can_still_pass_or_request_small_difference_review(monkeypatch,third_passed,expected):
    async def validation(s):
        if s['repairs']<3:return {'passed':False,'feedback':{'browser_passed':True,'uiproof':{'states':[{'ratio':.3}]}}}
        return {'passed':third_passed,'feedback':{'browser_passed':True,'uiproof':{'states':[{'ratio':0 if third_passed else .08}]}}}
    monkeypatch.setattr(workflow,'validate',validation)
    r=await workflow.build(InMemorySaver()).ainvoke(state(wants_design=False),{'configurable':{'thread_id':'third-result'}})
    assert r['repairs']==3 and not r.get('generation_stopped')
    if expected=='review_gate':assert r['__interrupt__'][0].value['node']=='review'
    else:assert r['passed'] and '__interrupt__' not in r


@pytest.mark.asyncio
async def test_stopped_task_is_terminal_and_cannot_resume(monkeypatch):
    from httpx import AsyncClient,ASGITransport
    from backend.main import app
    async def large(s):return {'passed':False,'feedback':{'browser_passed':True,'uiproof':{'states':[{'ratio':.3}]}}}
    monkeypatch.setattr(workflow,'validate',large)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            result=(await client.post('/api/projects',json={'prompt':'待办应用','demo':True,'wants_design':False})).json()
            pid,tid=result['project_id'],result['task_id']
            for _ in range(100):
                project=(await client.get('/api/projects/'+pid)).json()
                if project['tasks'][-1]['status']=='stopped':break
                await asyncio.sleep(.02)
            assert project['tasks'][-1]['status']=='stopped'
            assert not project.get('current_code_id')
            assert (await client.post('/api/tasks/'+tid+'/resume',json={})).status_code==400
            stream=await client.get('/api/tasks/'+tid+'/events')
            assert workflow.GENERATION_FAILURE_MESSAGE in stream.text
            assert 'event: settled' in stream.text


@pytest.mark.asyncio
async def test_unfinished_project_can_be_opened_and_permanently_deleted():
    from httpx import AsyncClient,ASGITransport
    from backend.main import app
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            first=(await client.post('/api/projects',json={'prompt':'待确认设计','demo':True,'wants_design':True})).json()
            second=(await client.post('/api/projects',json={'prompt':'保留的项目','demo':True,'wants_design':True})).json()
            for _ in range(100):
                project=(await client.get('/api/projects/'+first['project_id'])).json()
                other=(await client.get('/api/projects/'+second['project_id'])).json()
                if project['tasks'][-1]['status']=='needs_input' and other['tasks'][-1]['status']=='needs_input':break
                await asyncio.sleep(.02)
            assert project['tasks'][-1]['status']=='needs_input'
            assert (await client.post('/api/projects/'+first['project_id']+'/delete',json={})).status_code==200
            assert (await client.get('/api/projects/'+first['project_id'])).status_code==404
            assert (await client.get('/api/projects/'+second['project_id'])).status_code==200
            assert (await app.state.graph.aget_state({'configurable':{'thread_id':second['task_id']}})).values
            assert not (await app.state.graph.aget_state({'configurable':{'thread_id':first['task_id']}})).values
