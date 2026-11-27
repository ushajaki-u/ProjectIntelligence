# Code

Working proof-of-concept code for Project Pulse. Two independent parts:

| Folder | What it is |
|---|---|
| [`project_intelligence/`](project_intelligence/) | The deterministic **forecast engine** — reads Jira, rolls up dates, classifies variance and Epic health, and produces a color-coded Excel audit + executive PowerPoint. |
| [`synthetic_jira_generator/`](synthetic_jira_generator/) | A **test-data generator** that builds a realistic synthetic program (with embedded data-quality test cases) and can load it into a test Jira — the harness used to validate the engine. |

> **Note:** this is a proof of concept built ahead of the full product-discovery
> steps. The governing rules it implements are in
> [`../BUSINESS_RULES.md`](../BUSINESS_RULES.md).

## Security

Credentials live only in local `config.json` / `synthetic_project_config.json`
files, which are **git-ignored**. Only the `*.example.json` templates
(placeholders) are tracked. Never commit a real API token.
