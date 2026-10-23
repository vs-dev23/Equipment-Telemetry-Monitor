# Bench Check: Lab Equipment Monitor

## Project focus

A CSE portfolio prototype for tracking temperature and vibration readings from small lab equipment. The app stores measurements, shows the latest condition for each equipment ID, and flags readings over clear limits.

I kept the alert logic rule-based because this project does not have labelled failure examples. That makes each alert easy to explain and avoids presenting a threshold check as machine-learning prediction.

## What it demonstrates

- **Python and FastAPI:** REST endpoints, input validation, and an interactive API reference.
- **SQL and SQLite:** persistent readings, full-history counts, grouped queries, and per-equipment summaries.
- **Data analysis:** averages, peaks, alert counts, and alert rate.
- **Frontend integration:** a form that posts readings, live dashboard updates, filters, and CSV export.

## Run on Windows

Open PowerShell and run:

```powershell
cd Equipment-Telemetry-Monitor
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Open http://127.0.0.1:8000. Use **Load sample** to generate synthetic readings or **Add reading** to enter one yourself. The app creates `telemetry.db` beside `main.py`. API docs are at http://127.0.0.1:8000/docs.

## Pages

- **Overview:** total readings, alert count, temperature trend, and equipment pulse.
- **Equipment:** latest values for each ID; add a reading from this page.
- **Telemetry Log:** filter by equipment or condition and export matching rows to CSV.
- **Analytics:** SQL averages, peaks, and alert rates grouped by equipment.
- **API Lab:** endpoint guide, database health check, request example, and FastAPI docs link.

## API routes

- `GET /api/summary` - full-history counts, latest readings, and flagged reading count.
- `GET /api/readings?limit=100` - recent readings (up to 500).
- `GET /api/analytics` - overall and per-equipment SQL aggregates.
- `GET /api/health` - check API-to-database connectivity.
- `POST /api/readings` - validate and save a reading.
- `POST /api/demo-data?count=120` - add synthetic sample readings.
- `DELETE /api/readings` - clear the local demo database.

Example POST body:

```json
{
  "machine_id": "LAB-MOTOR-01",
  "temperature": 68.5,
  "vibration": 2.4,
  "runtime_hours": 245.0
}
```

## Limits and next step

Sample data is synthetic; no physical sensor is connected by default. To use a device, have it send JSON to `POST /api/readings`. Current alert limits are 80°C and 7 mm/s. The red warning banner appears when an asset latest reading crosses either limit and links to the filtered log. These are example settings and should be adjusted for the equipment being monitored.

