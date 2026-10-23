# Bench Check — Lab Equipment Monitor

I built Bench Check as a small CSE project to explore how equipment readings can move through a web app. You can record temperature and vibration values, save them in a database, and review the latest readings on a dashboard. When a machine’s latest reading crosses a set limit, the app highlights it so it’s easy to spot.

The project brings together a Python backend, a browser-based dashboard, and a local database. I kept the alert rules simple and explainable so it’s clear why a reading is flagged.

## What you can do

- View recent temperature readings and each machine’s latest status.
- Add a reading from the dashboard.
- Filter the telemetry log and export matching rows to CSV.
- Compare averages, peak values, and alert counts on the analytics page.
- Explore the API and check the database connection in API Lab.

## What I used

- **Python and FastAPI** for the backend and REST API.
- **SQLite and SQL** to store and summarize readings.
- **HTML, CSS, and JavaScript** for the dashboard and its separate pages.
- **Pydantic** to validate data sent to the API.

## Run on Windows

Open Command Prompt or PowerShell in the project folder, then run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. The app creates `telemetry.db` beside `main.py` when it starts. Use **Load sample** to explore the dashboard, or choose **Add reading** to enter your own values.

The interactive API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Pages

- **Overview** — reading totals, alerts, a temperature chart, and the latest equipment readings.
- **Equipment** — current readings for each equipment ID.
- **Telemetry Log** — searchable readings with status filters and CSV export.
- **Analytics** — averages, peaks, and alert counts for the stored readings.
- **API Lab** — endpoint guide, example request, and database connection check.

## API routes

| Method | Route | What it does |
| --- | --- | --- |
| `GET` | `/api/summary` | Returns totals, latest readings, and the flagged-reading count. |
| `GET` | `/api/readings?limit=100` | Returns recent readings; the limit can be up to 500. |
| `GET` | `/api/analytics` | Returns overall and per-equipment summaries. |
| `GET` | `/api/health` | Checks the API and database connection. |
| `POST` | `/api/readings` | Validates and saves a reading. |
| `POST` | `/api/demo-data?count=120` | Adds readings for trying out the dashboard. |
| `DELETE` | `/api/readings` | Clears the local readings database. |

Example body for `POST /api/readings`:

```json
{
  "machine_id": "LAB-MOTOR-01",
  "temperature": 68.5,
  "vibration": 2.4,
  "runtime_hours": 245.0
}
```
