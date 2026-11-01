import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from .config import DATA, initialize

def now():
    return datetime.now(timezone.utc).isoformat()

def connection():
    initialize()
    db = sqlite3.connect(DATA / 'workspace.sqlite3', timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL, updated TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, pages TEXT NOT NULL, created TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, job TEXT, action TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL)')
    return db

def save_job(job):
    with connection() as db:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,content=excluded.content,updated=excluded.updated', (job['id'], job.get('title','New contract'), json.dumps(job, ensure_ascii=False), now()))
    return job

def get_job(job_id):
    with connection() as db:
        row = db.execute('SELECT content FROM jobs WHERE id=?', (job_id,)).fetchone()
    if not row:
        raise ValueError('This workspace was not found.')
    return json.loads(row['content'])

def jobs():
    with connection() as db:
        rows = db.execute('SELECT id,title,updated FROM jobs ORDER BY updated DESC').fetchall()
    return [dict(r) for r in rows]

def add_source(name, role, path, pages):
    source_id = uuid.uuid4().hex
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    source = {'id':source_id,'name':name,'role':role,'path':str(path),'sha256':digest,'pages':pages,'created':now()}
    with connection() as db:
        db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?)',(source_id,name,role,str(path),digest,json.dumps(pages,ensure_ascii=False),source['created']))
    return source

def get_source(source_id):
    with connection() as db:
        row = db.execute('SELECT * FROM sources WHERE id=?', (source_id,)).fetchone()
    if not row:
        raise ValueError('Source not found.')
    result = dict(row)
    result['pages'] = json.loads(result['pages'])
    return result

def audit(job_id, action, detail):
    with connection() as db:
        db.execute('INSERT INTO audit(job,action,detail,created) VALUES (?,?,?,?)',(job_id,action,json.dumps(detail,ensure_ascii=False),now()))
