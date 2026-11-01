"""Project memory with optimistic revisions and immutable task snapshots."""
import json
from . import store


def lines(value):
    if not isinstance(value,list):return []
    return [item.strip() for item in value if isinstance(item,str) and item.strip() and len(item)<=2000][:100]


def read(project_id):
    with store.conn() as c:
        row = c.execute('SELECT revision,content FROM project_memory WHERE project_id=?',(project_id,)).fetchone()
        if row:
            return {**json.loads(row['content']), 'revision':row['revision']}
        first=c.execute('SELECT payload FROM tasks WHERE project_id=? ORDER BY created LIMIT 1',(project_id,)).fetchone()
        latest=c.execute("SELECT a.content FROM artifacts a JOIN tasks t ON t.id=a.task_id WHERE t.project_id=? AND a.kind='requirements' ORDER BY a.created DESC LIMIT 1",(project_id,)).fetchone()
    req=json.loads(latest['content']) if latest else {}
    return {'revision':0,'goal':json.loads(first['payload'])['prompt'] if first else '', 'features':lines(req.get('features',[])),'design_constraints':lines(req.get('design_constraints',[])),'protected_items':lines(req.get('protected_items',[])),'changes':[]}


def write(project_id, content, expected_revision):
    with store.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT revision FROM project_memory WHERE project_id=?',(project_id,)).fetchone()
        current=row['revision'] if row else 0
        if current!=expected_revision:
            raise ValueError('项目记忆已更新，请刷新后再保存')
        revision=current+1
        data={k:v for k,v in content.items() if k!='revision'}
        c.execute('INSERT OR REPLACE INTO project_memory VALUES(?,?,?)',(project_id,revision,json.dumps(data,ensure_ascii=False)))
        c.execute('INSERT INTO memory_versions VALUES(?,?,?,?)',(project_id,revision,json.dumps(data,ensure_ascii=False),store.now()))
    return {**data,'revision':revision}


def complete(state):
    pid=state['project_id']
    with store.conn() as c:
        if not c.execute('SELECT id FROM projects WHERE id=?',(pid,)).fetchone():return
    current=read(pid)
    if any(x['task_id']==state['task_id'] for x in current['changes']):return
    req=state.get('requirements',{})
    # User-maintained constraints stay authoritative; only implemented feature lists
    # are learned from successful deliveries against the same memory revision.
    if current['revision']==state.get('memory',{}).get('revision',0):
        current['features']=list(dict.fromkeys(current['features']+lines(req.get('features'))))
        if not current['design_constraints']:current['design_constraints']=lines(req.get('design_constraints',[]))
        if not current['protected_items']:current['protected_items']=lines(req.get('protected_items',[]))
    current['changes'].append({'task_id':state['task_id'],'request':state['prompt'],'code_id':state['code_id'],'created':store.now()})
    write(pid,current,current['revision'])
