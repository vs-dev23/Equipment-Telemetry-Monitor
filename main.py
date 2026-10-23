from __future__ import annotations

import random
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "telemetry.db"


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def initialize() -> None:
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            temperature REAL NOT NULL,
            vibration REAL NOT NULL,
            runtime_hours REAL NOT NULL
        )""")


class ReadingIn(BaseModel):
    machine_id: str = Field(min_length=1, max_length=40)
    temperature: float = Field(ge=-40, le=250)
    vibration: float = Field(ge=0, le=100)
    runtime_hours: float = Field(ge=0)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize()
    yield


app = FastAPI(title="Equipment Telemetry Monitor", version="1.0.0", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return HTML


@app.get("/api/readings")
def list_readings(limit: int = 100):
    limit = max(1, min(limit, 500))
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM readings ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


@app.get("/api/summary")
def summary():
    with connect() as db:
        total = db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        machines = db.execute("SELECT COUNT(DISTINCT machine_id) FROM readings").fetchone()[0]
        alerts = db.execute(
            "SELECT COUNT(*) FROM readings WHERE temperature >= 80 OR vibration >= 7"
        ).fetchone()[0]
        latest = db.execute("""
            SELECT r.* FROM readings AS r
            JOIN (SELECT machine_id, MAX(id) AS latest_id FROM readings GROUP BY machine_id) AS newest
            ON r.id = newest.latest_id ORDER BY r.machine_id
        """).fetchall()
        recent_alerts = db.execute(
            "SELECT * FROM readings WHERE temperature >= 80 OR vibration >= 7 ORDER BY id DESC LIMIT 10"
        ).fetchall()
    return {
        "total_readings": total,
        "machines_monitored": machines,
        "active_alerts": alerts,
        "latest_by_machine": [dict(row) for row in latest],
        "recent_alerts": [dict(row) for row in recent_alerts],
        "thresholds": {"temperature": 80, "vibration": 7},
    }


@app.get("/api/analytics")
def analytics():
    with connect() as db:
        overall = db.execute("""
            SELECT COUNT(*) AS total,
                   ROUND(AVG(temperature), 2) AS average_temperature,
                   ROUND(MAX(temperature), 2) AS peak_temperature,
                   ROUND(AVG(vibration), 2) AS average_vibration,
                   SUM(CASE WHEN temperature >= 80 OR vibration >= 7 THEN 1 ELSE 0 END) AS alert_count
            FROM readings
        """).fetchone()
        by_machine = db.execute("""
            SELECT machine_id, COUNT(*) AS readings,
                   ROUND(AVG(temperature), 2) AS average_temperature,
                   ROUND(MAX(temperature), 2) AS peak_temperature,
                   ROUND(AVG(vibration), 2) AS average_vibration,
                   SUM(CASE WHEN temperature >= 80 OR vibration >= 7 THEN 1 ELSE 0 END) AS alert_count
            FROM readings GROUP BY machine_id ORDER BY alert_count DESC, machine_id
        """).fetchall()
    result = dict(overall)
    result["alert_rate"] = round((result["alert_count"] or 0) / result["total"] * 100, 1) if result["total"] else 0
    result["by_machine"] = [dict(row) for row in by_machine]
    return result


@app.get("/api/health")
def health():
    with connect() as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok", "database": "connected"}


@app.post("/api/readings", status_code=201)
def create_reading(reading: ReadingIn):
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO readings (machine_id, recorded_at, temperature, vibration, runtime_hours) VALUES (?, ?, ?, ?, ?)",
            (reading.machine_id, recorded_at, reading.temperature, reading.vibration, reading.runtime_hours),
        )
        row = db.execute("SELECT * FROM readings WHERE id = ?", (cursor.lastrowid,)).fetchone()
    result = dict(row)
    result["alert"] = reading.temperature >= 80 or reading.vibration >= 7
    return result


@app.post("/api/demo-data")
def generate_demo_data(count: int = 120):
    if not 1 <= count <= 1000:
        raise HTTPException(status_code=400, detail="count must be between 1 and 1000")
    rng = random.Random()
    machines = ["PUMP-01", "MOTOR-02", "FAN-03"]
    now = datetime.now(timezone.utc)
    records = []
    for i in range(count):
        machine = machines[i % len(machines)]
        # A few deliberate spikes make the alert view useful in a demo.
        spike = i % 23 == 0 or i == count - 1
        temp = rng.uniform(82, 96) if spike else rng.uniform(44, 73)
        vibration = rng.uniform(7.2, 10) if spike else rng.uniform(0.4, 5.8)
        runtime = 240 + i * 0.25 + rng.uniform(0, 0.2)
        timestamp = (now - timedelta(minutes=(count - i) * 5)).isoformat(timespec="seconds")
        records.append((machine, timestamp, round(temp, 1), round(vibration, 2), round(runtime, 1)))
    with connect() as db:
        db.executemany(
            "INSERT INTO readings (machine_id, recorded_at, temperature, vibration, runtime_hours) VALUES (?, ?, ?, ?, ?)",
            records,
        )
    return {"inserted": count, "machines": machines, "message": "Demo readings added."}


@app.delete("/api/readings")
def clear_readings():
    with connect() as db:
        db.execute("DELETE FROM readings")
    return {"message": "All readings cleared."}


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bench Check | Lab equipment monitor</title>
<style>
:root{--canvas:#f6f6f2;--paper:#fff;--ink:#1d2925;--muted:#7b8781;--line:#e9ece8;--forest:#173b32;--forest2:#214b40;--lime:#d5f17a;--green:#25805b;--green-soft:#eaf5ee;--amber:#b87924;--amber-soft:#fff3df;--red:#bd594b;--red-soft:#fff0ed;--shadow:0 10px 34px rgba(32,54,43,.055)}*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.5 Inter,"Aptos",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}.shell{min-height:100vh;display:grid;grid-template-columns:238px minmax(0,1fr)}.rail{background:var(--forest);color:#fff;padding:26px 17px 20px;display:flex;flex-direction:column;min-height:100vh}.brand{display:flex;align-items:center;gap:11px;padding:2px 8px 34px}.brand-mark{width:35px;height:35px;border-radius:11px;background:var(--lime);display:grid;place-items:center;color:var(--forest);font-size:17px;font-weight:900}.brand-name{font-size:16px;font-weight:760;letter-spacing:-.03em}.brand-sub{font-size:10px;color:#b7c9c0;letter-spacing:.14em;text-transform:uppercase;margin-top:1px}.nav-label{font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:#9bb6aa;padding:0 11px;margin:6px 0 9px}.nav-item{display:flex;align-items:center;gap:11px;padding:10px 11px;border-radius:9px;color:#d5e2dc;margin:2px 0;font-weight:560;text-decoration:none;transition:background .15s}.nav-item:hover{background:#1c4439}.nav-item.active{background:var(--forest2);color:white}.nav-icon{width:18px;text-align:center;color:#b7d281;font-size:15px}.rail-spacer{flex:1}.rail-note{border:1px solid #3e6156;border-radius:12px;padding:14px 13px;background:#1b4439}.rail-note strong{display:block;font-size:12px;margin-bottom:4px}.rail-note p{font-size:11px;color:#bdd0c6;margin:0;line-height:1.55}.user{display:flex;align-items:center;gap:10px;padding:17px 7px 0;margin-top:18px;border-top:1px solid #3c5b51}.avatar{width:32px;height:32px;border-radius:50%;background:#476a58;display:grid;place-items:center;color:#e9f2d2;font-size:11px;font-weight:800}.user-name{font-size:12px;font-weight:650}.user-role{font-size:10px;color:#b7c9c0}.main{max-width:1440px;width:100%;margin:0 auto;padding:34px 46px 48px}.topline{display:flex;justify-content:space-between;align-items:center;margin-bottom:28px}.crumb{font-size:12px;color:var(--muted)}.crumb b{color:var(--ink);font-weight:650}.top-actions{display:flex;align-items:center;gap:10px}.live{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:11px;margin-right:9px}.live-dot{width:7px;height:7px;border-radius:50%;background:#53a879;box-shadow:0 0 0 3px #53a87920}.btn{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:9px;padding:10px 14px;background:white;color:var(--ink);font-family:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:.18s}.btn:hover{border-color:#cbd4cd;transform:translateY(-1px)}.btn.primary{background:var(--forest);border-color:var(--forest);color:white}.btn.primary:hover{background:#245344}.btn:disabled{opacity:.6;cursor:wait;transform:none}.heading{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:24px}.kicker{color:var(--green);font-size:10px;text-transform:uppercase;letter-spacing:.14em;font-weight:800}.heading h1{font-size:31px;letter-spacing:-.045em;line-height:1.14;margin:6px 0 7px;font-weight:720}.heading p{margin:0;color:var(--muted);font-size:13px}.period{font-size:11px;color:var(--muted);padding:9px 12px;border:1px solid var(--line);border-radius:8px;background:#fbfcfa;white-space:nowrap}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:16px}.metric{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:17px 19px;box-shadow:var(--shadow)}.metric-top{display:flex;justify-content:space-between;align-items:center}.metric-label{font-size:11px;color:var(--muted);font-weight:560}.metric-icon{height:27px;width:27px;border-radius:8px;background:#f2f5ef;display:grid;place-items:center;color:var(--green);font-size:13px}.metric-value{font-size:28px;letter-spacing:-.04em;font-weight:720;margin-top:8px;line-height:1.1}.metric-foot{font-size:10px;color:var(--muted);margin-top:6px}.metric-foot.good{color:var(--green)}.metric-foot.warn{color:var(--amber)}.content-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(270px,.85fr);gap:15px;margin-bottom:15px}.panel{background:var(--paper);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}.panel-pad{padding:19px 20px}.panel-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.panel-title{font-size:13px;font-weight:720;letter-spacing:-.01em}.panel-sub{font-size:10px;color:var(--muted);margin-top:3px}.tag{display:flex;align-items:center;gap:6px;border-radius:100px;padding:5px 8px;background:#f4f6f3;color:var(--muted);font-size:9px;white-space:nowrap}.tag-dot{width:6px;height:6px;border-radius:50%;background:#75a98a}.chart-wrap{margin-top:16px;height:214px;position:relative}.chart{width:100%;height:100%;overflow:visible}.chart-grid{stroke:#edf0eb;stroke-width:1}.chart-threshold{stroke:#d7964d;stroke-width:1;stroke-dasharray:4 5}.chart-fill{fill:url(#area)}.chart-line{fill:none;stroke:#3d8264;stroke-width:2.3;stroke-linecap:round;stroke-linejoin:round}.chart-alert{fill:#fff;stroke:#c56a51;stroke-width:2}.chart-y{fill:#98a19b;font-size:9px}.chart-x{fill:#98a19b;font-size:9px}.threshold-label{fill:#ad762e;font-size:9px}.chart-legend{display:flex;align-items:center;gap:15px;margin-top:9px;color:var(--muted);font-size:10px}.legend-item{display:flex;align-items:center;gap:6px}.legend-line{width:14px;height:2px;background:#3d8264}.legend-dash{width:14px;border-top:1px dashed #d7964d}.trend-note{margin-left:auto;color:#a3aaa5;font-size:9px}.machines{display:flex;flex-direction:column;gap:9px;margin-top:16px}.machine{border:1px solid #edf0eb;background:#fcfcfa;border-radius:9px;padding:12px 12px 11px}.machine-head{display:flex;justify-content:space-between;align-items:center}.machine-name{font-size:11px;font-weight:700}.machine-type{font-size:9px;color:var(--muted);margin-top:1px}.status{font-size:9px;font-weight:700;padding:4px 7px;border-radius:100px;background:var(--green-soft);color:var(--green)}.status.alert{background:var(--amber-soft);color:var(--amber)}.machine-readout{display:flex;align-items:flex-end;justify-content:space-between;margin-top:10px}.machine-temp{font-size:22px;font-weight:700;letter-spacing:-.04em;line-height:1}.machine-temp small{font-size:10px;color:var(--muted);font-weight:500;letter-spacing:0}.machine-vibe{text-align:right;color:var(--muted);font-size:9px}.machine-vibe b{font-size:11px;color:var(--ink);font-weight:650}.machine-line{height:3px;border-radius:4px;background:#e9eee8;margin-top:10px;overflow:hidden}.machine-line span{display:block;height:100%;border-radius:4px;background:#83b394}.machine-line span.alert{background:#d89959}.table-panel{margin-bottom:15px}.table-wrap{overflow-x:auto;margin-top:13px}table{width:100%;border-collapse:collapse;text-align:left;white-space:nowrap}th{font-size:9px;color:#909a93;text-transform:uppercase;letter-spacing:.08em;font-weight:700;padding:9px 10px;border-bottom:1px solid var(--line)}td{font-size:10px;color:#4f5c55;padding:11px 10px;border-bottom:1px solid #f0f2ef}tr:last-child td{border-bottom:0}.asset{display:flex;align-items:center;gap:8px}.asset-icon{width:25px;height:25px;border-radius:7px;background:#eff4ec;display:grid;place-items:center;color:#5b8268;font-size:11px}.asset b{font-size:10px;color:var(--ink)}.asset small{display:block;font-size:9px;color:var(--muted);margin-top:1px}.reading-hot{color:var(--amber);font-weight:700}.status-cell{font-size:9px;font-weight:700;color:var(--green)}.status-cell.alert{color:var(--amber)}.empty{color:var(--muted);padding:26px;text-align:center;font-size:11px}.warning-banner{display:none;align-items:center;gap:12px;padding:12px 14px;margin:-10px 0 18px;border:1px solid #e9b2aa;border-left:4px solid #c24c40;border-radius:10px;background:#fff0ed;color:#84372f}.warning-banner.show{display:flex}body.warning-active{--canvas:#fff0ed;--forest:#7b2924;--forest2:#963a32;--green:#b74136;--green-soft:#fde8e5;--line:#edc7c1;--shadow:0 10px 34px rgba(131,38,30,.10)}body.warning-active .warning-banner.show{background:#c8372d;border-color:#a92720;color:#fff;box-shadow:0 5px 18px #9d2d2430}body.warning-active .warning-copy span{color:#ffe1dc}body.warning-active .warning-banner .btn{background:#fff;color:#8f251e;border-color:#f5cac4}body.warning-active .live{color:#9c2d26}.warning-icon{width:27px;height:27px;flex:0 0 27px;border-radius:50%;display:grid;place-items:center;background:#c24c40;color:white;font-weight:800}.warning-copy{flex:1;min-width:0}.warning-copy strong{display:block;font-size:11px}.warning-copy span{font-size:10px;color:#96564e}.warning-assets{font-size:9px;color:#84372f;max-width:250px}.live-dot.warning{background:#c24c40;box-shadow:0 0 0 3px #c24c4020}.warning-banner .btn{background:#fff;border-color:#e3c4bf;color:#84372f}.view{display:none}.view.active{display:block}.filterbar{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 12px}.filterbar input,.filterbar select{border:1px solid var(--line);border-radius:8px;background:white;padding:9px 10px;font-family:inherit;font-size:11px;color:var(--ink)}.mini-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.mini-stat{padding:15px;border:1px solid var(--line);background:#fff;border-radius:10px}.mini-stat span{font-size:10px;color:var(--muted)}.mini-stat strong{display:block;font-size:23px;margin-top:5px}.endpoint-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:14px}.endpoint{padding:13px;border:1px solid var(--line);border-radius:9px;background:#fcfcfa}.endpoint code{font-size:11px;font-weight:700}.endpoint p{font-size:10px;color:var(--muted);margin:5px 0 0}.method{font-size:8px;font-weight:800;border-radius:4px;padding:3px 5px;background:#e9f4ed;color:var(--green)}.method.post{background:#edf0ff;color:#5968bc}.callout{font-size:10px;background:#f7faef;padding:11px;border-radius:8px;margin-top:12px;color:#65724f}.code-sample{background:#162b25;color:#e0efe4;border-radius:8px;padding:13px;font:10px/1.65 Consolas,monospace;white-space:pre-wrap}.api-status{font-size:10px;color:var(--muted);margin-top:9px}.api-status.ok{color:var(--green)}.filter-count{margin-left:auto;color:var(--muted);font-size:10px}.bottom-note{display:flex;justify-content:space-between;gap:12px;color:#8c9690;font-size:9px;padding:2px 2px}.bottom-note b{color:#65736a;font-weight:650}dialog{border:1px solid var(--line);border-radius:14px;padding:0;width:min(440px,calc(100% - 28px));box-shadow:0 25px 80px #10251d40;color:var(--ink)}dialog::backdrop{background:#10251d88;backdrop-filter:blur(3px)}.dialog-inner{padding:22px}.dialog-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px}.dialog-head h2{font-size:18px;letter-spacing:-.03em;margin:0}.dialog-head p{font-size:11px;color:var(--muted);margin:5px 0 0}.dialog-close{border:0;background:#f2f4f0;border-radius:50%;width:30px;height:30px;cursor:pointer;color:var(--ink);font-size:17px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:12px}.field{display:flex;flex-direction:column;gap:5px}.field.full{grid-column:1/-1}.field label{font-size:10px;font-weight:700;color:#56645b}.field input{width:100%;border:1px solid #dfe5df;background:#fcfdfb;border-radius:8px;padding:10px;font-family:inherit;font-size:13px;color:var(--ink);outline:none}.field input:focus{border-color:#70a485;box-shadow:0 0 0 3px #70a48520}.field-help{font-size:9px;color:var(--muted)}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}.toast{position:fixed;right:22px;bottom:20px;padding:11px 15px;background:var(--forest);color:#fff;border-radius:9px;font-size:11px;box-shadow:0 8px 24px #18382d30;opacity:0;transform:translateY(8px);transition:.2s;pointer-events:none}.toast.show{opacity:1;transform:translateY(0)}
@media(max-width:1000px){.shell{grid-template-columns:205px minmax(0,1fr)}.main{padding:28px 25px 36px}.content-grid{grid-template-columns:minmax(0,1.4fr) minmax(240px,.9fr)}}@media(max-width:760px){.shell{display:block}.rail{min-height:0;height:auto;padding:12px 15px;flex-direction:row;align-items:center;justify-content:space-between}.brand{padding:0}.nav-label,.rail-spacer,.rail-note,.user{display:none}.rail{overflow-x:auto;justify-content:flex-start;gap:4px}.nav-item{display:inline-flex;padding:7px 8px;margin:2px;white-space:nowrap}.main{padding:24px 15px}.topline{margin-bottom:22px}.heading{align-items:flex-start;flex-direction:column}.heading h1{font-size:27px}.metrics{gap:8px}.metric{padding:13px 12px}.metric-value{font-size:23px}.metric-foot{font-size:9px}.content-grid{grid-template-columns:1fr}.period{display:none}.top-actions .live{font-size:0;margin-right:0}.panel-pad{padding:16px}.warning-banner{display:none;align-items:center;gap:12px;padding:12px 14px;margin:-10px 0 18px;border:1px solid #e9b2aa;border-left:4px solid #c24c40;border-radius:10px;background:#fff0ed;color:#84372f}.warning-banner.show{display:flex}body.warning-active{--canvas:#fff0ed;--forest:#7b2924;--forest2:#963a32;--green:#b74136;--green-soft:#fde8e5;--line:#edc7c1;--shadow:0 10px 34px rgba(131,38,30,.10)}body.warning-active .warning-banner.show{background:#c8372d;border-color:#a92720;color:#fff;box-shadow:0 5px 18px #9d2d2430}body.warning-active .warning-copy span{color:#ffe1dc}body.warning-active .warning-banner .btn{background:#fff;color:#8f251e;border-color:#f5cac4}body.warning-active .live{color:#9c2d26}.warning-icon{width:27px;height:27px;flex:0 0 27px;border-radius:50%;display:grid;place-items:center;background:#c24c40;color:white;font-weight:800}.warning-copy{flex:1;min-width:0}.warning-copy strong{display:block;font-size:11px}.warning-copy span{font-size:10px;color:#96564e}.warning-assets{font-size:9px;color:#84372f;max-width:250px}.live-dot.warning{background:#c24c40;box-shadow:0 0 0 3px #c24c4020}.warning-banner .btn{background:#fff;border-color:#e3c4bf;color:#84372f}.view{display:none}.view.active{display:block}.filterbar{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 12px}.filterbar input,.filterbar select{border:1px solid var(--line);border-radius:8px;background:white;padding:9px 10px;font-family:inherit;font-size:11px;color:var(--ink)}.mini-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.mini-stat{padding:15px;border:1px solid var(--line);background:#fff;border-radius:10px}.mini-stat span{font-size:10px;color:var(--muted)}.mini-stat strong{display:block;font-size:23px;margin-top:5px}.endpoint-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:14px}.endpoint{padding:13px;border:1px solid var(--line);border-radius:9px;background:#fcfcfa}.endpoint code{font-size:11px;font-weight:700}.endpoint p{font-size:10px;color:var(--muted);margin:5px 0 0}.method{font-size:8px;font-weight:800;border-radius:4px;padding:3px 5px;background:#e9f4ed;color:var(--green)}.method.post{background:#edf0ff;color:#5968bc}.callout{font-size:10px;background:#f7faef;padding:11px;border-radius:8px;margin-top:12px;color:#65724f}.code-sample{background:#162b25;color:#e0efe4;border-radius:8px;padding:13px;font:10px/1.65 Consolas,monospace;white-space:pre-wrap}.api-status{font-size:10px;color:var(--muted);margin-top:9px}.api-status.ok{color:var(--green)}.filter-count{margin-left:auto;color:var(--muted);font-size:10px}.mini-grid{grid-template-columns:repeat(2,1fr)}.endpoint-grid{grid-template-columns:1fr}.bottom-note{flex-direction:column}.table-wrap{margin-left:-5px;margin-right:-5px}}@media(max-width:420px){.metrics{grid-template-columns:1fr}.metric{display:flex;justify-content:space-between;align-items:center}.metric-value{font-size:21px;margin:0}.metric-foot{display:none}.metric-top{gap:8px}.heading h1{font-size:24px}.btn{padding:9px 10px;font-size:10px}}
</style>
</head>
<body>
<div class="shell">
<aside class="rail">
<div class="brand"><div class="brand-mark">M</div><div><div class="brand-name">Bench Check</div><div class="brand-sub">lab equipment monitor</div></div></div>
<div class="nav-label">Project pages</div><a class="nav-item active" href="#" data-page="overview"><span class="nav-icon">◫</span>Overview</a><a class="nav-item" href="#" data-page="equipment"><span class="nav-icon">⌁</span>Equipment</a><a class="nav-item" href="#" data-page="telemetry"><span class="nav-icon">▤</span>Telemetry log</a><a class="nav-item" href="#" data-page="analytics"><span class="nav-icon">⌁</span>Analytics</a><a class="nav-item" href="#" data-page="api"><span class="nav-icon">{ }</span>API Lab</a>
<div class="rail-spacer"></div><div class="rail-note"><strong>Project focus</strong><p>Logging heat and vibration on small lab equipment, with alert limits you can explain.</p></div><div class="user"><div class="avatar">VS</div><div><div class="user-name">Vartika Singh</div><div class="user-role">CSE portfolio project</div></div></div>
</aside>
<main class="main">
<div class="topline"><div class="crumb">Workspace <span style="padding:0 6px;color:#bac1bc">/</span> <b id="crumb">Overview</b></div><div class="top-actions"><div class="live"><i class="live-dot"></i><span id="liveText">Connecting to monitor</span></div><button class="btn" id="refresh"><span>↻</span> Refresh</button><button class="btn" id="seed"><span>✦</span> Load sample</button><button class="btn primary" id="recordBtn"><span>＋</span> Add reading</button></div></div>
<div class="warning-banner" id="warningBanner" role="alert" aria-live="polite"><span class="warning-icon">!</span><div class="warning-copy"><strong id="warningTitle">Current reading warning</strong><span id="warningDetails"></span></div><button class="btn" id="warningReview">View flagged readings →</button></div><section class="view active" id="page-overview"><header class="heading"><div><div class="kicker">Lab equipment · prototype</div><h1>Keep an eye on the lab equipment.</h1><p>Log temperature and vibration, then review readings that cross the set limits.</p></div><div class="period">◷ &nbsp; Latest 60 measurements</div></header>
<section class="metrics"><article class="metric"><div><div class="metric-top"><span class="metric-label">Readings collected</span><span class="metric-icon">⌁</span></div><div class="metric-value" id="total">—</div><div class="metric-foot">Stored in your local database</div></div></article><article class="metric"><div><div class="metric-top"><span class="metric-label">Equipment monitored</span><span class="metric-icon">▦</span></div><div class="metric-value" id="machinesCount">—</div><div class="metric-foot good" id="machineFoot">Your connected assets</div></div></article><article class="metric"><div><div class="metric-top"><span class="metric-label">Needs a closer look</span><span class="metric-icon">⌑</span></div><div class="metric-value" id="alerts">—</div><div class="metric-foot warn">Readings above set thresholds</div></div></article></section>
<section class="content-grid"><article class="panel panel-pad"><div class="panel-head"><div><div class="panel-title">Temperature over time</div><div class="panel-sub">Recent sensor readings across all equipment</div></div><span class="tag"><i class="tag-dot"></i> Updated just now</span></div><div class="chart-wrap" id="chartArea"><svg class="chart" id="chart" viewBox="0 0 760 220" preserveAspectRatio="none" aria-label="Temperature trend chart"></svg></div><div class="chart-legend"><span class="legend-item"><i class="legend-line"></i>Temperature</span><span class="legend-item"><i class="legend-dash"></i>Alert level · 80°C</span><span class="trend-note">°C</span></div></article>
<article class="panel panel-pad" id="equipmentPulse"><div class="panel-head"><div><div class="panel-title">Equipment pulse</div><div class="panel-sub">Most recent reading from each asset</div></div><span class="tag" id="pulseTag">— assets</span></div><div class="machines" id="machines"></div></article></section>
<article class="panel panel-pad" style="margin-top:14px"><div class="panel-head"><div><div class="panel-title">A note on the design</div><div class="panel-sub">Why this prototype uses visible limits</div></div></div><p class="panel-sub" style="font-size:11px;line-height:1.75;color:var(--ink);max-width:850px">The demo has no labelled examples of equipment failure, so it uses simple temperature and vibration limits instead of claiming to predict breakdowns. Each flagged reading can be checked against the values in the log. Sample data is generated for practice; real readings can be sent through the API.</p></article></section><section class="view" id="page-equipment"><header class="heading"><div><div class="kicker">Asset register</div><h1>Equipment</h1><p>Review each asset latest signal and operating condition.</p></div><button class="btn primary" id="equipmentAdd">＋ Record reading</button></header><div class="machines" id="equipmentCards"></div><div class="bottom-note">Equipment appears here after its first reading is saved.</div></section><section class="view" id="page-telemetry"><header class="heading"><div><div class="kicker">Data records</div><h1>Telemetry log</h1><p>Search, filter, and export recent sensor readings.</p></div><span class="period">Saved readings · latest 500</span></header><section class="panel panel-pad table-panel" id="activity"><div class="panel-head"><div><div class="panel-title">Recent readings</div><div class="panel-sub">Measurements saved by the monitor</div></div><span class="tag">Auto-refreshes every 15 sec</span></div><div class="filterbar"><input id="readingSearch" type="search" placeholder="Find equipment ID…"><select id="statusFilter"><option value="">All conditions</option><option value="normal">Within limits</option><option value="alert">Needs review</option></select><button class="btn" id="exportCsv">↓ Export CSV</button><span class="filter-count" id="filteredCount">Showing latest readings</span></div><div class="table-wrap"><table><thead><tr><th>Equipment</th><th>Time</th><th>Temperature</th><th>Vibration</th><th>Run time</th><th>Condition</th></tr></thead><tbody id="rows"></tbody></table></div></section>
</section><section class="view" id="page-analytics"><header class="heading"><div><div class="kicker">Data analysis</div><h1>Analytics</h1><p>SQL aggregates calculated from your stored sensor history.</p></div></header><section class="panel" id="analytics" style="margin:18px 0"><div class="panel-head"><div><div class="panel-title">Analytics &amp; SQL insights</div><div class="panel-sub">Aggregates are calculated from the full reading history by the FastAPI backend.</div></div><button class="btn" id="recalculate">↻ Recalculate</button></div><div class="mini-grid"><div class="mini-stat"><span>Average temperature</span><strong id="avgTemp">—</strong></div><div class="mini-stat"><span>Peak temperature</span><strong id="peakTemp">—</strong></div><div class="mini-stat"><span>Average vibration</span><strong id="avgVibration">—</strong></div><div class="mini-stat"><span>Alert rate</span><strong id="alertRate">—</strong></div></div><div class="table-wrap"><table><thead><tr><th>Equipment</th><th>Samples</th><th>Average temp</th><th>Peak temp</th><th>Average vibration</th><th>Alerts</th></tr></thead><tbody id="analyticsRows"></tbody></table></div><div class="callout">Explainable rule: flag a reading at ≥80°C or ≥7 mm/s vibration. This is threshold monitoring, not machine-learning prediction.</div></section>
</section><section class="view" id="page-api"><header class="heading"><div><div class="kicker">Backend &amp; integration</div><h1>API Lab</h1><p>Inspect endpoints, database connectivity, and an example sensor request.</p></div></header><section class="panel" id="api" style="margin:18px 0"><div class="panel-head"><div><div class="panel-title">API &amp; integration lab</div><div class="panel-sub">Connect a sensor or inspect the documented endpoints.</div></div><a class="btn primary" href="/docs" target="_blank" rel="noreferrer">Open FastAPI docs ↗</a></div><div class="endpoint-grid"><div class="endpoint"><span class="method">GET</span> <code>/api/summary</code><p>Dashboard totals, latest asset readings, and alert counts.</p></div><div class="endpoint"><span class="method">GET</span> <code>/api/readings</code><p>Read recent stored measurements (limit up to 500).</p></div><div class="endpoint"><span class="method">GET</span> <code>/api/analytics</code><p>SQL aggregates overall and grouped by equipment.</p></div><div class="endpoint"><span class="method">GET</span> <code>/api/health</code><p>Check API and database connectivity.</p></div><div class="endpoint"><span class="method post">POST</span> <code>/api/readings</code><p>Validate and save a sensor reading.</p></div><div class="endpoint"><span class="method post">POST</span> <code>/api/demo-data</code><p>Generate varied sample data for a repeatable demo.</p></div></div><div class="content-grid" style="margin-top:14px"><div><div class="panel-sub" style="margin-bottom:7px">Example POST body</div><pre class="code-sample" id="sampleJson">{
  "machine_id": "PUMP-01",
  "temperature": 68.5,
  "vibration": 2.4,
  "runtime_hours": 245.0
}</pre><button class="btn" id="copyJson">Copy request JSON</button></div><div><div class="panel-sub" style="margin-bottom:7px">Connection check</div><p class="panel-sub">Test that the API can query the local SQLite database.</p><button class="btn" id="testApi">Test API &amp; database</button><div class="api-status" id="apiResult">No check run yet.</div></div></div><div class="callout">Skills shown: Python/FastAPI, request validation, SQL/SQLite, data aggregation, JavaScript API integration, filtering, and CSV export.</div></section>
</section></main></div><dialog id="readingDialog"><form id="readingForm" class="dialog-inner"><div class="dialog-head"><div><h2>Record a sensor reading</h2><p>Save a new measurement to the local equipment log.</p></div><button type="button" class="dialog-close" id="closeDialog" aria-label="Close">×</button></div><div class="fields"><div class="field full"><label for="machineId">Equipment ID</label><input id="machineId" name="machine_id" value="PUMP-01" maxlength="40" required><span class="field-help">Use an existing ID or enter a new equipment name.</span></div><div class="field"><label for="temperature">Temperature (°C)</label><input id="temperature" name="temperature" type="number" min="-40" max="250" step="0.1" placeholder="68.5" required></div><div class="field"><label for="vibration">Vibration (mm/s)</label><input id="vibration" name="vibration" type="number" min="0" max="100" step="0.01" placeholder="2.4" required></div><div class="field full"><label for="runtime">Runtime (hours)</label><input id="runtime" name="runtime_hours" type="number" min="0" step="0.1" placeholder="245.0" required></div></div><div class="dialog-actions"><button type="button" class="btn" id="cancelDialog">Cancel</button><button type="submit" class="btn primary" id="saveReading">Save reading</button></div></form></dialog><div class="toast" id="toast"></div>
<script>
const $=id=>document.getElementById(id);let toastTimer;let allReadings=[];const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function showToast(message){const el=$('toast');el.textContent=message;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),2600)}
function renderChart(data){const svg=$('chart');if(!data.length){svg.innerHTML='<text x="380" y="112" text-anchor="middle" fill="#8b958e" font-size="12">Add sample data to see the temperature story.</text>';return}const W=760,H=220,L=36,R=8,T=14,B=24,plotW=W-L-R,plotH=H-T-B;const y=v=>T+plotH-(v/110)*plotH;let grid='';[0,25,50,75,100].forEach(v=>{grid+=`<line class="chart-grid" x1="${L}" y1="${y(v)}" x2="${W-R}" y2="${y(v)}"/><text class="chart-y" x="0" y="${y(v)+3}">${v}</text>`});const pts=data.map((d,i)=>({x:L+(data.length===1?plotW/2:i*plotW/(data.length-1)),y:y(d.temperature),v:d.temperature}));const path=pts.map((p,i)=>`${i?'L':'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');const area=`${path} L ${pts[pts.length-1].x},${T+plotH} L ${pts[0].x},${T+plotH} Z`;const markers=pts.filter(p=>p.v>=80).map(p=>`<circle class="chart-alert" cx="${p.x}" cy="${p.y}" r="3.5"><title>Alert reading: ${p.v}°C</title></circle>`).join('');svg.innerHTML=`<defs><linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#78a98b" stop-opacity=".2"/><stop offset="100%" stop-color="#78a98b" stop-opacity="0"/></linearGradient></defs>${grid}<line class="chart-threshold" x1="${L}" y1="${y(80)}" x2="${W-R}" y2="${y(80)}"/><text class="threshold-label" x="${W-R-78}" y="${y(80)-5}">80° alert</text><path class="chart-fill" d="${area}"/><path class="chart-line" d="${path}"/>${markers}<text class="chart-x" x="${L}" y="${H-3}">Earlier</text><text class="chart-x" x="${W-R}" y="${H-3}" text-anchor="end">Latest</text>`}
function renderMachines(items,target='machines'){if(target==='machines')$('pulseTag').textContent=`${items.length} asset${items.length===1?'':'s'}`;if(!items.length){$(target).innerHTML='<div class="empty">No equipment readings yet. Add a reading or load sample data.</div>';return}const icons={'PUMP':'↗','MOTOR':'⟳','FAN':'✳'};$(target).innerHTML=items.map(m=>{const hot=m.temperature>=80||m.vibration>=7;const type=m.machine_id.split('-')[0];return `<article class="machine"><div class="machine-head"><div><div class="machine-name">${icons[type]||'◈'} &nbsp;${esc(m.machine_id)}</div><div class="machine-type">${type==='PUMP'?'Water circulation':type==='MOTOR'?'Drive unit':type==='FAN'?'Air handling':'Equipment'} · latest reading</div></div><span class="status ${hot?'alert':''}">${hot?'Needs review':'Within limits'}</span></div><div class="machine-readout"><div class="machine-temp">${m.temperature.toFixed(1)}<small> °C</small></div><div class="machine-vibe">Vibration<br><b>${m.vibration.toFixed(2)} mm/s</b></div></div><div class="machine-line"><span class="${hot?'alert':''}" style="width:${Math.min(m.temperature,100)}%"></span></div><div style="margin-top:9px;color:var(--muted);font-size:9px">${m.runtime_hours.toFixed(1)} runtime hours</div></article>`}).join('')}async function load(){try{const [s,r]=await Promise.all([fetch('/api/summary').then(x=>{if(!x.ok)throw Error('summary');return x.json()}),fetch('/api/readings?limit=500').then(x=>{if(!x.ok)throw Error('readings');return x.json()})]);allReadings=r;$('liveText').textContent='Monitor is up';updateWarning(s.latest_by_machine||[]);$('total').textContent=s.total_readings.toLocaleString();$('machinesCount').textContent=s.machines_monitored;$('machineFoot').textContent=s.machines_monitored?'Latest status from your equipment':'Waiting for first readings';$('alerts').textContent=s.active_alerts.toLocaleString();const data=r.slice(-60);renderChart(data);renderMachines(s.latest_by_machine||[]);renderMachines(s.latest_by_machine||[],'equipmentCards');const latest=[...r].reverse().slice(0,8);$('rows').innerHTML=latest.length?latest.map(x=>{const hot=x.temperature>=80||x.vibration>=7;const type=x.machine_id.split('-')[0];return `<tr><td><div class="asset"><span class="asset-icon">${type==='PUMP'?'↗':type==='MOTOR'?'⟳':'✳'}</span><span><b>${esc(x.machine_id)}</b><small>${type==='PUMP'?'Water circulation':type==='MOTOR'?'Drive unit':'Air handling'}</small></span></div></td><td>${new Date(x.recorded_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</td><td class="${x.temperature>=80?'reading-hot':''}">${x.temperature.toFixed(1)}°C</td><td class="${x.vibration>=7?'reading-hot':''}">${x.vibration.toFixed(2)} mm/s</td><td>${x.runtime_hours.toFixed(1)} h</td><td><span class="status-cell ${hot?'alert':''}">${hot?'Needs review':'Running well'}</span></td></tr>`}).join(''):'<tr><td colspan="6" class="empty">Nothing to report yet. Add sample data to see equipment readings here.</td></tr>';applyReadingFilters()}catch(e){$('liveText').textContent='Monitor unavailable';console.error(e)}}
function updateWarning(items){const affected=items.filter(x=>x.temperature>=80||x.vibration>=7);document.body.classList.toggle('warning-active',affected.length>0);const banner=$('warningBanner');banner.classList.toggle('show',affected.length>0);const dot=document.querySelector('.live-dot');dot.classList.toggle('warning',affected.length>0);if(affected.length){$('liveText').textContent='Warning active';$('warningTitle').textContent=`Current warning: ${affected.length} asset${affected.length===1?'':'s'} outside limits`;$('warningDetails').textContent=affected.map(x=>`${x.machine_id} · ${Number(x.temperature).toFixed(1)}°C · ${Number(x.vibration).toFixed(2)} mm/s`).join('  |  ')}else{$('liveText').textContent='Monitor is up'}}
$('warningReview').onclick=()=>{switchPage('telemetry');$('readingSearch').value='';$('statusFilter').value='alert';applyReadingFilters()};function filteredReadings(){const query=$('readingSearch').value.trim().toLowerCase(),condition=$('statusFilter').value;return allReadings.slice().reverse().filter(x=>(!query||x.machine_id.toLowerCase().includes(query))&&(!condition||(condition==='alert'?(x.temperature>=80||x.vibration>=7):(x.temperature<80&&x.vibration<7))))}
function applyReadingFilters(){const rows=filteredReadings().slice(0,100);$('filteredCount').textContent=`Showing ${rows.length} matching readings`;$('rows').innerHTML=rows.length?rows.map(x=>{const alert=x.temperature>=80||x.vibration>=7;return `<tr><td><div class="asset"><span class="asset-icon">${x.machine_id.startsWith('PUMP')?'↗':x.machine_id.startsWith('MOTOR')?'⟳':'✳'}</span><span><b>${esc(x.machine_id)}</b><small>${x.machine_id.startsWith('PUMP')?'Water circulation':x.machine_id.startsWith('MOTOR')?'Drive unit':'Equipment'}</small></span></div></td><td>${new Date(x.recorded_at).toLocaleString()}</td><td class="${x.temperature>=80?'reading-hot':''}">${Number(x.temperature).toFixed(1)}°C</td><td class="${x.vibration>=7?'reading-hot':''}">${Number(x.vibration).toFixed(2)} mm/s</td><td>${Number(x.runtime_hours).toFixed(1)} h</td><td><span class="status-cell ${alert?'alert':''}">${alert?'Needs review':'Within limits'}</span></td></tr>`}).join(''):'<tr><td colspan="6" class="empty">No readings match those filters.</td></tr>'}
async function loadAnalytics(){try{const a=await fetch('/api/analytics').then(r=>r.json());$('avgTemp').textContent=a.average_temperature==null?'—':a.average_temperature.toFixed(1)+'°C';$('peakTemp').textContent=a.peak_temperature==null?'—':a.peak_temperature.toFixed(1)+'°C';$('avgVibration').textContent=a.average_vibration==null?'—':a.average_vibration.toFixed(2)+' mm/s';$('alertRate').textContent=(a.alert_rate||0).toFixed(1)+'%';$('analyticsRows').innerHTML=a.by_machine.length?a.by_machine.map(m=>`<tr><td><b>${esc(m.machine_id)}</b></td><td>${m.readings}</td><td>${m.average_temperature}°C</td><td>${m.peak_temperature}°C</td><td>${m.average_vibration} mm/s</td><td class="${m.alert_count?'reading-hot':''}">${m.alert_count}</td></tr>`).join(''):'<tr><td colspan="6" class="empty">Add readings to calculate metrics.</td></tr>'}catch(e){showToast('Analytics could not load. Check the API connection.')}}
$('readingSearch').oninput=applyReadingFilters;$('statusFilter').onchange=applyReadingFilters;$('exportCsv').onclick=()=>{const rows=filteredReadings();if(!rows.length){showToast('No readings match the selected filters.');return}const cols=['machine_id','recorded_at','temperature','vibration','runtime_hours'];const csv=[cols.join(','),...rows.map(r=>cols.map(k=>'"'+String(r[k]).replaceAll('"','""')+'"').join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));const a=document.createElement('a');a.href=url;a.download='telemetry-readings.csv';a.click();URL.revokeObjectURL(url);showToast(`${rows.length} readings exported.`)};$('recalculate').onclick=async()=>{await loadAnalytics();showToast('Analytics recalculated from stored readings.')};$('testApi').onclick=async()=>{const out=$('apiResult');out.textContent='Checking API and database…';try{const r=await fetch('/api/health').then(x=>x.json());out.className='api-status ok';out.textContent=`API ${r.status} · SQLite ${r.database}`}catch(e){out.className='api-status';out.textContent='Could not reach the API. Start the server and retry.'}};$('copyJson').onclick=async()=>{try{await navigator.clipboard.writeText($('sampleJson').textContent);showToast('Example request JSON copied.')}catch(e){showToast('Clipboard unavailable. Select the JSON to copy it.')}};$('recordBtn').onclick=()=>$('readingDialog').showModal();$('closeDialog').onclick=()=>$('readingDialog').close();$('cancelDialog').onclick=()=>$('readingDialog').close();$('readingForm').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;const b=$('saveReading');const payload={machine_id:form.machine_id.value.trim(),temperature:Number(form.temperature.value),vibration:Number(form.vibration.value),runtime_hours:Number(form.runtime_hours.value)};b.disabled=true;b.textContent='Saving…';try{const response=await fetch('/api/readings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!response.ok){const detail=await response.json();throw Error(detail.detail||'Could not save reading')}form.reset();form.machine_id.value='PUMP-01';$('readingDialog').close();await load();await loadAnalytics();showToast('Reading saved to the equipment log.')}catch(error){showToast(error.message||'Could not save this reading.')}finally{b.disabled=false;b.textContent='Save reading'}};function switchPage(name){document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='page-'+name));document.querySelectorAll('.nav-item').forEach(a=>a.classList.toggle('active',a.dataset.page===name));const names={overview:'Overview',equipment:'Equipment',telemetry:'Telemetry log',analytics:'Analytics',api:'API Lab'};$('crumb').textContent=names[name]||'Overview';window.scrollTo({top:0,behavior:'smooth'});if(name==='telemetry')applyReadingFilters();if(name==='analytics')loadAnalytics()}document.querySelectorAll('.nav-item').forEach(link=>link.addEventListener('click',e=>{e.preventDefault();switchPage(link.dataset.page)}));$('equipmentAdd').onclick=()=>$('readingDialog').showModal();$('seed').onclick=async()=>{const b=$('seed');b.disabled=true;b.innerHTML='<span>…</span> Generating sample';try{const res=await fetch('/api/demo-data?count=120',{method:'POST'});if(!res.ok)throw Error('Could not add data');await load();await loadAnalytics();showToast('Sample readings added. Take a look around.')}catch(e){showToast('Could not reach the monitor. Is the server running?')}finally{b.disabled=false;b.innerHTML='<span>✦</span> Load sample'}};$('refresh').onclick=async()=>{await load();await loadAnalytics();showToast('View refreshed')};load();loadAnalytics();setInterval(()=>{load();loadAnalytics()},15000);
</script></body></html>'''

















