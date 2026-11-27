# Project Pulse — Forecast Engine

A deterministic, explainable delivery-forecasting engine. It reads a program's
Epic hierarchy from Jira, rolls up dates bottom-up, classifies schedule
variance, runs Epic-health and data-quality checks, and produces a color-coded
Excel audit trail and a two-slide executive PowerPoint.

Every result traces back to a numbered rule — see
[`../../BUSINESS_RULES.md`](../../BUSINESS_RULES.md).

## What it produces
- **Excel** (`project_forecast_report.xlsx`) — full work-item hierarchy with a
  collapsible 4-level outline, plus a Final Report sheet with the project
  forecast, Epic health, and data-quality findings.
- **PowerPoint** (`project_forecast_executive_summary.pptx`) — slide 1: delivery
  outlook and data-quality cards; slide 2: open-Epic forecast and exception table.

## Setup
1. Copy the template and fill in your own Jira details:
   ```bash
   cp config.example.json config.json
   ```
   `config.json` is git-ignored — your API token never gets committed.
2. In `config.json`, set `jira.base_url`, `jira.email`, `jira.api_token`,
   and the `project.project_key` / `project.labels` / `project.delivery_date`.
3. Install dependencies:
   ```bash
   pip install requests openpyxl python-pptx
   ```

## Run
```bash
python forecast_engine.py
```
The Excel and PowerPoint files are written next to the script.

## Configuration notes
- `project.labels` — one or more Jira labels (a list). Epics carrying **any** of
  them are included (the labels are OR'd together in the Jira query). A single
  string (`"label": "phase-1"`) still works for the one-label case.
- `forecasting` — `max_depth`, excluded statuses, Orange/Red variance thresholds
  (days), and the minimum due-date coverage percent.
- `epic_health_check` — the Blocked / Backlog status names and the
  release-warning window.
- `holiday_warnings` — standard company/location holidays only (no individual
  PTO). Informational; does not alter forecast dates.
- `team_locations` — maps assignees to a location code for holiday warnings.

## Security
Never commit a real API token. Keep real credentials in `config.json` (ignored
by git); only `config.example.json` (placeholders) is tracked.
