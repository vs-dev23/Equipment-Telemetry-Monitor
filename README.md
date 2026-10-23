# Bench Check: Lab Equipment Monitor

A CSE portfolio project for logging temperature and vibration readings from lab equipment. Bench Check stores measurements in SQLite, shows the latest condition for each equipment ID, and highlights readings that cross configurable example limits.

## Project focus

The alerts use clear, rule-based thresholds. The project has no labelled equipment failure data, so it does not claim to predict failures with machine learning. This keeps each warning easy to explain and verify.

## Skills demonstrated

- **Python and FastAPI:** REST endpoints, request validation, and interactive API documentation.
- **SQL and SQLite:** persistent storage, grouped queries, and per-equipment summaries.
- **Data analysis:** averages, peak values, alert counts, and alert rates.
- **Frontend integration:** dashboard updates, data entry, search and status filters, and CSV export.

## Run on Windows

Open Command Prompt or PowerShell in the project folder and run these commands one at a time:

```powershell
py -m venv .venv
\.venv\Scripts\python.exe -m pip install -r requirements.txt
\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The app creates `telemetry.db` beside `main.py` the first time it runs.

Use **Load sample** to add synthetic readings, or **Add reading** to enter a measurement. The interactive API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Dashboard pages

- **Overview:** reading totals, current alerts, temperature trend, and latest equipment readings.
- **Equipment:** latest status by equipment ID and a shortcut to add readings.
- **Telemetry Log:** filter readings by equipment or alert status and export the results to CSV.
- **Analytics:** averages, peaks, and alert rates overall and by equipment.
- **API Lab:** endpoint guide, database health check, and an example sensor request.

## API routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/summary` | Reading totals, latest readings, and flagged-reading count. |
| `GET` | `/api/readings?limit=100` | Recent stored measurements; limit can be up to 500. |
| `GET` | `/api/analytics` | Overall and per-equipment SQL aggregates. |
| `GET` | `/api/health` | Check API and database connectivity. |
| `POST` | `/api/readings` | Validate and save a sensor reading. |
| `POST` | `/api/demo-data?count=120` | Add synthetic readings for a demonstration. |
| `DELETE` | `/api/readings` | Clear the local demo database. |

Example request body for `POST /api/readings`:

```json
{
  "machine_id": "LAB-MOTOR-01",
  "temperature": 68.5,
  "vibration": 2.4,
  "runtime_hours": 245.0
}
```

