# Code

The deterministic forecasting engine will live here.

Planned contents:

- **`project_forecaster.py`** — the engine: Jira hierarchy extraction, recursive date roll-up, data-quality gates, Epic Health Check, and the Excel + executive-deck outputs.
- **`config.example.json`** — a configuration template with placeholder values.

> **Security note:** the real configuration file (containing a Jira URL, email, and API token) is **never** committed. A `.gitignore` will keep it out of version control, and only the sanitized `config.example.json` is shared here.
