"""Durable installation queue; distinct from runtime inference jobs."""
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime, timezone

import docker
from fastapi import HTTPException
from controller import settings as s
from controller import adapters, model_manager
from controller.catalog import CATALOG

lock = threading.RLock()
halt = threading.Event()
thread = None


def sql(statement, params=()):
    with closing(sqlite3.connect(s.STATE / 'installations.sqlite', timeout=10)) as connection, connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(statement, params)
        return [dict(row) for row in cursor.fetchall()] if cursor.description else []


def start():
    global thread
    s.STATE.mkdir(parents=True, exist_ok=True)
    sql('''CREATE TABLE IF NOT EXISTS operations (
        id TEXT PRIMARY KEY, kind TEXT, target TEXT, tool TEXT, state TEXT,
        message TEXT, progress INTEGER, created TEXT)''')
    sql("UPDATE operations SET state='failed', message='Gateway restarted during installation. Retry safely; existing data is preserved.' WHERE state='running'")
    halt.clear()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def stop():
    halt.set()
    if thread:
        thread.join(timeout=3)


def active(tool):
    return sql("SELECT * FROM operations WHERE tool=? AND state IN ('queued','running')", (tool,))


def submit(kind, target):
    if adapters.MODE != 'managed':
        raise HTTPException(409, 'Installation and model changes are disabled in external mode; existing files remain untouched')
    if kind == 'tool':
        tool = target
        adapters.adapter(tool)
    elif kind in {'model', 'remove-model'} and target in CATALOG:
        tool = CATALOG[target]['tool']
    else:
        raise HTTPException(404, 'Unknown catalogue entry')
    with lock:
        current = active(tool)
        if current:
            if current[0]['kind'] == kind and current[0]['target'] == target:
                return current[0]
            raise HTTPException(409, 'An installation operation is already pending for this tool')
        try:
            c = adapters.adapter(tool).inspect(docker.from_env())
            if c.status == 'running':
                raise HTTPException(409, 'Stop the workload before installing or changing its models')
        except docker.errors.NotFound:
            pass
        except docker.errors.DockerException:
            raise HTTPException(503, 'Docker Engine unavailable')
        id = uuid.uuid4().hex
        sql('INSERT INTO operations VALUES (?,?,?,?,?,?,?,?)',
            (id, kind, target, tool, 'queued', 'Waiting to install', None, datetime.now(timezone.utc).isoformat()))
        return sql('SELECT * FROM operations WHERE id=?', (id,))[0]


def worker():
    while not halt.is_set():
        with lock:
            rows = sql("SELECT * FROM operations WHERE state='queued' ORDER BY created LIMIT 1")
            if rows:
                job = rows[0]
                sql("UPDATE operations SET state='running' WHERE id=?", (job['id'],))
        if not rows:
            halt.wait(1)
            continue
        def progress(message, percent):
            sql('UPDATE operations SET message=?, progress=? WHERE id=?', (message, percent, job['id']))
        try:
            if job['kind'] == 'tool':
                adapters.adapter(job['target']).provision(docker.from_env(timeout=1800), progress)
            elif job['kind'] == 'model':
                model_manager.install(job['target'], progress)
            else:
                model_manager.remove(job['target'], progress)
            sql("UPDATE operations SET state='completed', progress=100 WHERE id=?", (job['id'],))
        except Exception as exc:
            message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            sql("UPDATE operations SET state='failed', message=? WHERE id=?", (message[:4000], job['id']))
