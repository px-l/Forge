import json, os, sqlite3, uuid
from pathlib import Path
from datetime import datetime, timezone

DATA = Path(os.getenv("DATA_DIR", "./data"))
DATA.mkdir(exist_ok=True, parents=True)
DB = DATA / "forge.db"


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid.uuid4())


def conn():
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    with conn() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,owner TEXT,name TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, project_id TEXT, status TEXT, payload TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT,payload TEXT);
        CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,task_id TEXT,kind TEXT,content TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS project_memory(project_id TEXT PRIMARY KEY, revision INTEGER, content TEXT);
        CREATE TABLE IF NOT EXISTS memory_versions(project_id TEXT,revision INTEGER,content TEXT,created TEXT,PRIMARY KEY(project_id,revision));
        CREATE TABLE IF NOT EXISTS preview_links(digest TEXT PRIMARY KEY,code_id TEXT,created TEXT);
        CREATE INDEX IF NOT EXISTS task_events ON events(task_id,id);""")
        if "current_code_id" not in [
            r["name"] for r in c.execute("PRAGMA table_info(projects)")
        ]:
            c.execute("ALTER TABLE projects ADD COLUMN current_code_id TEXT DEFAULT ''")
        if "deleted_at" not in [r["name"] for r in c.execute("PRAGMA table_info(projects)")]:
            c.execute("ALTER TABLE projects ADD COLUMN deleted_at TEXT DEFAULT NULL")


def set_current(project_id, code_id):
    with conn() as c:
        c.execute(
            "UPDATE projects SET current_code_id=? WHERE id=?", (code_id, project_id)
        )


def event(task_id, **payload):
    with conn() as c:
        c.execute(
            "INSERT INTO events(task_id,payload) VALUES(?,?)",
            (task_id, json.dumps({**payload, "time": now()}, ensure_ascii=False)),
        )


def status(task_id, value):
    with conn() as c:
        c.execute("UPDATE tasks SET status=? WHERE id=?", (value, task_id))
    event(task_id, type="status", status=value)


def artifact(task_id, kind, content):
    aid = uid()
    with conn() as c:
        c.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?,?)",
            (aid, task_id, kind, json.dumps(content, ensure_ascii=False), now()),
        )
    event(task_id, type="artifact", kind=kind, artifact_id=aid)
    return aid


def get_artifact(aid):
    with conn() as c:
        r = c.execute("SELECT * FROM artifacts WHERE id=?", (aid,)).fetchone()
    return {**dict(r), "content": json.loads(r["content"])} if r else None
