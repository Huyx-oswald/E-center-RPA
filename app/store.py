"""SQLite 存储层：流程(flows) 与 运行记录(runs)。标准库 sqlite3，不引 ORM。"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = os.path.abspath(
    os.environ.get("LANYIN_DB", os.path.join(os.path.dirname(__file__), "..", "data", "lanyin.db"))
)

# ponytail: 单进程 MVP 用一把全局写锁挡住 sqlite 并发写；要扩容再换 WAL/连接池。
_write_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS flows(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                steps TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flow_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                log TEXT NOT NULL DEFAULT '',
                result TEXT NOT NULL DEFAULT '{}',
                screenshot TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT
            );
            """
        )


def _flow_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "steps": json.loads(row["steps"]),
        "created_at": row["created_at"],
    }


def _run_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "flow_id": row["flow_id"],
        "status": row["status"],
        "log": row["log"],
        "result": json.loads(row["result"]),
        "screenshot": row["screenshot"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def list_flows() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM flows ORDER BY id DESC").fetchall()
    return [_flow_row(r) for r in rows]


def get_flow(flow_id: int):
    with _conn() as c:
        row = c.execute("SELECT * FROM flows WHERE id=?", (flow_id,)).fetchone()
    return _flow_row(row) if row else None


def save_flow(flow_id, name: str, steps: list) -> int:
    steps_json = json.dumps(steps, ensure_ascii=False)
    with _write_lock, _conn() as c:
        if flow_id:
            c.execute("UPDATE flows SET name=?, steps=? WHERE id=?", (name, steps_json, flow_id))
            return int(flow_id)
        cur = c.execute(
            "INSERT INTO flows(name, steps, created_at) VALUES(?,?,?)",
            (name, steps_json, _now()),
        )
        return cur.lastrowid


def delete_flow(flow_id: int) -> None:
    with _write_lock, _conn() as c:
        c.execute("DELETE FROM flows WHERE id=?", (flow_id,))


def create_run(flow_id: int) -> int:
    with _write_lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO runs(flow_id, status, started_at) VALUES(?,?,?)",
            (flow_id, "running", _now()),
        )
        return cur.lastrowid


def append_log(run_id: int, line: str) -> None:
    with _write_lock, _conn() as c:
        c.execute("UPDATE runs SET log = log || ? WHERE id=?", (line + "\n", run_id))


def finish_run(run_id: int, status: str, result: dict, screenshot: str | None = None) -> None:
    with _write_lock, _conn() as c:
        c.execute(
            "UPDATE runs SET status=?, result=?, screenshot=?, finished_at=? WHERE id=?",
            (status, json.dumps(result, ensure_ascii=False), screenshot, _now(), run_id),
        )


def get_run(run_id: int):
    with _conn() as c:
        row = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return _run_row(row) if row else None


def list_runs(flow_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM runs WHERE flow_id=? ORDER BY id DESC LIMIT 20", (flow_id,)
        ).fetchall()
    return [_run_row(r) for r in rows]
