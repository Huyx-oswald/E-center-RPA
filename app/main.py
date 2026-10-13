"""lanyin-rpa 服务端：FastAPI 提供 API + 托管前端静态页。"""

import os
import threading

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import store
from .engine import SCREENSHOT_DIR, run_flow

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="lanyin-rpa")
store.init_db()
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def _execute(run_id: int, steps: list) -> None:
    def on_log(line: str) -> None:
        store.append_log(run_id, line)

    try:
        result, screenshot = run_flow(steps, run_id, on_log)
        store.finish_run(run_id, "success", result, screenshot)
    except Exception as e:  # 引擎异常 -> 记录并标记失败，不让线程崩掉
        store.append_log(run_id, f"ERROR: {type(e).__name__}: {e}")
        store.finish_run(run_id, "error", {})


@app.get("/api/flows")
def api_list_flows():
    return store.list_flows()


@app.post("/api/flows")
def api_save_flow(payload: dict = Body(...)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name 不能为空")
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        raise HTTPException(400, "steps 必须是数组")
    flow_id = store.save_flow(payload.get("id"), name, steps)
    return store.get_flow(flow_id)


@app.delete("/api/flows/{flow_id}")
def api_delete_flow(flow_id: int):
    if not store.get_flow(flow_id):
        raise HTTPException(404, "流程不存在")
    store.delete_flow(flow_id)
    return {"ok": True}


@app.post("/api/flows/{flow_id}/run")
def api_run_flow(flow_id: int):
    flow = store.get_flow(flow_id)
    if not flow:
        raise HTTPException(404, "流程不存在")
    run_id = store.create_run(flow_id)
    threading.Thread(target=_execute, args=(run_id, flow["steps"]), daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/flows/{flow_id}/runs")
def api_list_runs(flow_id: int):
    return store.list_runs(flow_id)


@app.get("/api/runs/{run_id}")
def api_get_run(run_id: int):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")
    return run


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/screenshots", StaticFiles(directory=SCREENSHOT_DIR), name="screenshots")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
