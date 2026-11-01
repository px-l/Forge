import asyncio, json, os, secrets, hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

load_dotenv()
from . import store, memory
from .workflow import build

workers: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app):
    store.init()
    with store.conn() as c:
        c.execute("UPDATE tasks SET status='interrupted' WHERE status IN ('running','queued')")
    async with AsyncSqliteSaver.from_conn_string(
        str(store.DATA / "checkpoints.db")
    ) as cp:
        app.state.graph = build(cp)
        yield
        pending = list(workers.values())
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


app = FastAPI(title="Forge Delivery API", lifespan=lifespan)


@app.middleware("http")
async def visitor(req: Request, call_next):
    token = req.cookies.get("forge_visitor", "")
    if len(token) != 64:
        token = secrets.token_hex(32)
    req.state.owner = token
    if req.method not in ("GET", "HEAD", "OPTIONS"):
        origin = req.headers.get("origin")
        allowed = {
            str(req.base_url).rstrip("/"),
            os.getenv("APP_ORIGIN", "http://localhost:5173"),
        }
        if origin and origin not in allowed:
            return Response("Origin not allowed", 403)
    res = await call_next(req)
    if req.cookies.get("forge_visitor") != token:
        res.set_cookie(
            "forge_visitor",
            token,
            httponly=True,
            samesite="strict",
            secure=req.url.scheme == "https",
            max_age=31536000,
        )
    if req.url.path in ("/", "/index.html"):
        res.headers["Cache-Control"] = "no-cache"
    res.headers["X-Content-Type-Options"] = "nosniff"
    return res


def owned(req, pid):
    with store.conn() as c:
        r = c.execute(
            "SELECT * FROM projects WHERE id=? AND owner=? AND deleted_at IS NULL", (pid, req.state.owner)
        ).fetchone()
    if not r:
        raise HTTPException(404, "项目不存在")
    return dict(r)


def task_owned(req, tid):
    with store.conn() as c:
        r = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not r:
        raise HTTPException(404, "任务不存在")
    owned(req, r["project_id"])
    return dict(r)


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "configured": bool(os.getenv("DASHSCOPE_API_KEY")),
        "model": os.getenv("CODE_MODEL", "qwen3.7-plus"),
        "runner": os.getenv("RUNNER_URL", "http://127.0.0.1:8011"),
    }


@app.get("/api/projects")
async def projects(req: Request):
    with store.conn() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT * FROM projects WHERE owner=? AND deleted_at IS NULL ORDER BY created DESC",
                (req.state.owner,),
            )
        ]


@app.post('/api/projects/{pid}/delete')
async def delete_project(req: Request, pid: str):
    owned(req,pid)
    with store.conn() as c:
        if c.execute("SELECT id FROM tasks WHERE project_id=? AND status IN ('queued','running')",(pid,)).fetchone():
            raise HTTPException(409,'项目正在执行，请先停止任务再删除')
        c.execute('UPDATE projects SET deleted_at=? WHERE id=?',(store.now(),pid))
        c.execute("UPDATE tasks SET status='cancelled' WHERE project_id=? AND status IN ('needs_input','interrupted')",(pid,))
    return {'ok':True}


@app.post('/api/projects/{pid}/undelete')
async def undelete_project(req: Request, pid: str):
    with store.conn() as c:
        row=c.execute('SELECT id FROM projects WHERE id=? AND owner=? AND deleted_at IS NOT NULL',(pid,req.state.owner)).fetchone()
        if not row:raise HTTPException(404,'项目不存在')
        c.execute('UPDATE projects SET deleted_at=NULL WHERE id=?',(pid,))
    return {'ok':True}


class MemoryInput(BaseModel):
    revision: int = Field(ge=0)
    goal: str = Field(max_length=12000)
    features: list[str] = Field(default_factory=list,max_length=100)
    design_constraints: list[str] = Field(default_factory=list,max_length=100)
    protected_items: list[str] = Field(default_factory=list,max_length=100)


@app.post('/api/projects/{pid}/memory')
async def save_memory(req: Request, pid: str, body: MemoryInput):
    owned(req,pid)
    if any(len(item)>2000 for values in [body.features,body.design_constraints,body.protected_items] for item in values):
        raise HTTPException(400,'每条记忆不能超过2000字')
    with store.conn() as c:
        if c.execute("SELECT id FROM tasks WHERE project_id=? AND status IN ('queued','running','needs_input','interrupted')",(pid,)).fetchone():
            raise HTTPException(409,'请先完成或取消当前任务，再编辑项目记忆')
    current=memory.read(pid)
    try:return memory.write(pid,{**body.model_dump(),'changes':current['changes']},body.revision)
    except ValueError as e:raise HTTPException(409,str(e))


class TaskInput(BaseModel):
    prompt: str = Field(min_length=2, max_length=12000)
    mode: str = "new"
    demo: bool = False
    wants_design: bool = False
    base_code_id: str | None = None


@app.post("/api/projects")
async def create(req: Request, body: TaskInput):
    pid = store.uid()
    with store.conn() as c:
        c.execute(
            "INSERT INTO projects(id,owner,name,created) VALUES(?,?,?,?)",
            (pid, req.state.owner, body.prompt[:28], store.now()),
        )
    return {"project_id": pid, **await new_task(req, pid, body)}


@app.get("/api/projects/{pid}")
async def project(req: Request, pid: str):
    p = owned(req, pid)
    with store.conn() as c:
        tasks = [
            dict(r)
            for r in c.execute(
                "SELECT id,status,payload,created FROM tasks WHERE project_id=? ORDER BY created",
                (pid,),
            )
        ]
        artifacts = [
            {**dict(r), "content": json.loads(r["content"])}
            for r in c.execute(
                "SELECT a.* FROM artifacts a JOIN tasks t ON a.task_id=t.id WHERE t.project_id=? ORDER BY a.created",
                (pid,),
            )
        ]
    return {**p, "tasks": tasks, "artifacts": artifacts, "memory":memory.read(pid)}


async def execute(tid, value):
    store.event(tid, type="attempt_started")
    store.status(tid, "running")
    try:
        result = await app.state.graph.ainvoke(
            value, {"configurable": {"thread_id": tid}, "recursion_limit": 24}
        )
        if result.get("__interrupt__"):
            store.event(
                tid, type="needs_input", request=result["__interrupt__"][0].value
            )
            store.status(tid, "needs_input")
        else:
            store.status(
                tid, "completed" if result.get("passed", True) or result.get("user_accepted") else "needs_review"
            )
    except asyncio.CancelledError:
        store.status(tid, "interrupted")
        raise
    except Exception as e:
        store.event(tid, type="error", message=str(e)[:700])
        store.status(tid, "failed")
    finally:
        workers.pop(tid, None)


def launch(tid, value):
    workers[tid] = asyncio.create_task(execute(tid, value))


@app.post("/api/projects/{pid}/tasks")
async def new_task(req: Request, pid: str, body: TaskInput):
    owned(req, pid)
    if len(workers) >= 4:
        raise HTTPException(429, "执行队列已满，请稍后再试")
    if body.mode not in ("new", "modify", "prototype"):
        raise HTTPException(400, "任务类型无效")
    with store.conn() as c:
        running = c.execute(
            "SELECT id FROM tasks WHERE project_id=? AND status IN ('running','queued','needs_input','interrupted')",
            (pid,),
        ).fetchone()
        if running:
            raise HTTPException(409, "当前项目有未结束任务，请先继续或取消")
    snapshot=memory.read(pid)
    if not snapshot["goal"]:snapshot["goal"]=body.prompt
    state = {
        "memory":snapshot,
        "task_id": store.uid(),
        "project_id": pid,
        "prompt": body.prompt,
        "mode": body.mode,
        "demo": body.demo,
        "wants_design": body.wants_design,
        "repairs": 0,
    }
    if body.mode == "modify":
        a = store.get_artifact(body.base_code_id or "")
        if not a or a["kind"] != "code":
            raise HTTPException(400, "请选择代码版本")
        t = task_owned(req, a["task_id"])
        if t["project_id"] != pid:
            raise HTTPException(400, "代码不属于当前项目")
        state["html"] = a["content"]["html"]
        prior = store.get_artifact(a["content"].get("requirement_id", ""))
        state["requirements"] = {
            **(prior["content"] if prior else {}),
            "change_request": body.prompt,
            "base_code_id": a["id"],
        }
        design = store.get_artifact(a["content"].get("design_id", ""))
        if design:
            state.update(
                {"target": design["content"]["image"], "design_id": design["id"], "design_spec":a["content"].get("design_spec") or design["content"].get("spec")}
            )
        state["requirement_id"] = store.artifact(
            state["task_id"], "requirements", state["requirements"]
        )
    state["memory_id"]=store.artifact(state["task_id"],"project_memory",snapshot)
    with store.conn() as c:
        c.execute(
            "INSERT INTO tasks VALUES(?,?,?,?,?)",
            (state["task_id"], pid, "queued", json.dumps(state), store.now()),
        )
    launch(state["task_id"], state)
    return {"task_id": state["task_id"]}


class RestoreInput(BaseModel):
    code_id: str


@app.post("/api/projects/{pid}/restore")
async def restore(req: Request, pid: str, body: RestoreInput):
    owned(req, pid)
    with store.conn() as c:
        if c.execute(
            "SELECT id FROM tasks WHERE project_id=? AND status IN ('running','queued')",
            (pid,),
        ).fetchone():
            raise HTTPException(409, "执行中不能恢复版本")
    a = store.get_artifact(body.code_id)
    if not a or a["kind"] != "code":
        raise HTTPException(404, "版本不存在")
    t = task_owned(req, a["task_id"])
    if t["project_id"] != pid:
        raise HTTPException(400, "版本不属于当前项目")
    store.set_current(pid, a["id"])
    store.event(
        a["task_id"],
        type="restored",
        code_id=a["id"],
        summary="用户恢复代码版本；业务数据保持不变",
    )
    return {"ok": True}


class ResumeInput(BaseModel):
    answer: dict | str | None = None


@app.post("/api/tasks/{tid}/resume")
async def resume(req: Request, tid: str, body: ResumeInput):
    t = task_owned(req, tid)
    if tid in workers:
        raise HTTPException(409, "任务正在执行")
    if t["status"] not in ("needs_input", "failed", "interrupted"):
        raise HTTPException(400, "任务当前不能恢复")
    if t["status"] == "needs_input" and body.answer is None:
        raise HTTPException(400, "请提供回答")
    launch(tid, Command(resume=body.answer) if t["status"] == "needs_input" else None)
    return {"ok": True}


@app.post("/api/tasks/{tid}/cancel")
async def cancel(req: Request, tid: str):
    task_owned(req, tid)
    if tid in workers:
        workers[tid].cancel()
        await asyncio.gather(workers[tid], return_exceptions=True)
    store.status(tid, "cancelled")
    return {"ok": True}


@app.get("/api/tasks/{tid}/events")
async def events(req: Request, tid: str, after: int = 0):
    task_owned(req, tid)
    try:
        cursor = max(after, int(req.headers.get("last-event-id", "0")))
    except ValueError:
        cursor = after

    async def stream():
        nonlocal cursor
        while not await req.is_disconnected():
            with store.conn() as c:
                rows = c.execute(
                    "SELECT * FROM events WHERE task_id=? AND id>? ORDER BY id",
                    (tid, cursor),
                ).fetchall()
                status = c.execute(
                    "SELECT status FROM tasks WHERE id=?", (tid,)
                ).fetchone()["status"]
            for r in rows:
                cursor = r["id"]
                yield f"id: {cursor}\ndata: {r['payload']}\n\n"
            if status not in ("running", "queued"):
                yield "event: settled\ndata: {}\n\n"
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/artifacts/{aid}/preview")
async def preview(req: Request, aid: str):
    a = store.get_artifact(aid)
    if not a or a["kind"] != "code":
        raise HTTPException(404)
    task_owned(req, a["task_id"])
    return HTMLResponse(
        a["content"]["html"],
        headers={
            "Content-Security-Policy": "sandbox allow-scripts allow-forms; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'"
        },
    )


@app.get("/api/artifacts/{aid}/download")
async def download(req: Request, aid: str):
    a = store.get_artifact(aid)
    if not a or a["kind"] != "code":
        raise HTTPException(404)
    task_owned(req, a["task_id"])
    return Response(
        a["content"]["html"],
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="index.html"'},
    )


@app.get("/api/artifacts/{aid}/report")
async def proof_report(req: Request, aid: str):
    a = store.get_artifact(aid)
    if not a or a["kind"] != "uiproof_report":
        raise HTTPException(404)
    task_owned(req, a["task_id"])
    return Response(a["content"]["html"], media_type="application/octet-stream", headers={"Content-Disposition": 'attachment; filename="uiproof-report.html"'})

@app.post("/api/artifacts/{aid}/share")
async def share_preview(req: Request, aid: str):
    a = store.get_artifact(aid)
    if not a or a["kind"] != "code":
        raise HTTPException(404)
    task_owned(req, a["task_id"])
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    with store.conn() as c:
        c.execute("INSERT INTO preview_links VALUES(?,?,?)", (digest, aid, store.now()))
    return {"url": str(req.base_url).rstrip('/') + '/p/' + token}


@app.get("/p/{token}")
async def shared_preview(token: str):
    digest = hashlib.sha256(token.encode()).hexdigest()
    with store.conn() as c:
        row = c.execute("SELECT l.code_id FROM preview_links l JOIN artifacts a ON a.id=l.code_id JOIN tasks t ON t.id=a.task_id JOIN projects p ON p.id=t.project_id WHERE l.digest=? AND p.deleted_at IS NULL", (digest,)).fetchone()
    a = store.get_artifact(row['code_id']) if row else None
    if not a:
        raise HTTPException(404)
    from .public_preview import render
    return HTMLResponse(render(a['content']['html'], digest), headers={"Cache-Control":"no-store", "Referrer-Policy":"no-referrer", "Content-Security-Policy":"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; frame-src 'self'; connect-src 'none'; form-action 'none'; base-uri 'none'"})


static = Path("forge/dist")
if static.exists():
    app.mount("/", StaticFiles(directory=static, html=True), name="web")
