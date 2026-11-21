# Business Rules

The forecast is not a black box. Every date, status, and health signal the engine produces is governed by an explicit, numbered rule — so any result can be traced back to the logic that produced it and the Jira data it came from.

There are two rule sets:

- **Forecast Rules (BR)** — how dates roll up and how delivery status is classified.
- **Epic Health Rules (EH)** — how delivery risk is surfaced, *separately* from the date forecast.

---

## Forecast Rules

| ID | Rule | Description |
|---|---|---|
| **BR-01** | Exclude Done and Deprecated work items | Done or Deprecated work items do not participate in forecast calculations or date roll-up; they remain visible for traceability. |
| **BR-02** | Use documented due date for active leaf items | For an active leaf, Calculated Due Date equals Documented Due Date; without a due date, it contributes no date upward. |
| **BR-03** | Roll up the latest active-child date | An active parent receives the latest calculated due date among its active, non-excluded children. |
| **BR-04** | Flag a Done Epic with active descendants | Classify as Data Issue (Orange) and do not calculate variance. |
| **BR-05** | Exclude a Done Epic with no active descendants | Classify as Excluded — Epic is Done; do not calculate variance. |
| **BR-06** | Exclude a Deprecated Epic | Classify as Excluded — Epic is Deprecated; do not calculate variance. |
| **BR-07** | Flag an active Epic when all descendants are Done | Classify as Review Required (Orange); confirm closure or undocumented work. |
| **BR-08** | Require minimum due-date coverage | Below the configured coverage threshold, classify as Insufficient Data and do not calculate variance. |
| **BR-09** | Require an Epic documented due date | Without an Epic due date, classify as Insufficient Data — Epic Due Date Missing. |
| **BR-10** | Require an Epic calculated due date | Without a rolled-up date, classify as Insufficient Data — No Calculated Date. |
| **BR-11** | Calculate Epic variance | Calculated Epic Due Date minus Documented Epic Due Date. |
| **BR-12** | Classify Epic forecast status | Apply configured Red and Orange thresholds; zero is On Target and negative is Ahead. |
| **BR-13** | Require minimum project due-date coverage | Below configured project coverage, do not calculate the project forecast date or variance. |
| **BR-14** | Include only forecast-eligible Epics | Only Epics passing data-quality, coverage, and date rules contribute to the project forecast. |
| **BR-15** | Select the later date for each eligible Epic | Use the later of the Epic's documented and calculated due dates. |
| **BR-16** | Calculate the project forecast date | Use the latest of the Project Delivery Date and the eligible Epic contribution dates. |
| **BR-17** | Calculate and classify project variance | Calculated Project Date minus Project Delivery Date; apply configured thresholds. |

---

## Epic Health Rules

Health indicators explain *why* delivery is at risk. They are reported as facts, and they never change the forecast date.

| ID | Rule | Description |
|---|---|---|
| **EH-01** | Run a health check for every open Epic | Every Epic not in an excluded status receives a health check, regardless of its forecast status. |
| **EH-02** | Skip closed or excluded Epics | Done and Deprecated Epics do not receive the health check; existing consistency rules still apply. |
| **EH-03** | Count blocked active descendants | Count active descendants whose status matches a configured Blocked status. |
| **EH-04** | Count backlog active descendants | Count active descendants whose status matches a configured Backlog status. |
| **EH-05** | Count backlog items without due dates | Count Backlog descendants that have no documented due date. |
| **EH-06** | Flag backlog near release | When the Epic due date — or the project delivery date, if the Epic date is absent — is within the configured warning window, count all Backlog descendants as near-release risk. |
| **EH-07** | Keep forecast and health separate | Epic health indicators explain delivery conditions but do not change the date forecast or variance classification. |
| **EH-08** | Report facts before scoring | Reports counts and an "Attention Required" message; it does not assign a numerical health score or a Red/Orange rating. |
| **EH-09** | Preserve other active statuses | Count active descendants outside the configured Blocked and Backlog statuses, so workflow states are never silently ignored. |

---

*17 forecast rules + 9 Epic-health rules = 26 governed rules. Thresholds, excluded statuses, blocked/backlog status names, and the release-warning window are all configurable — the rules stay constant; the parameters adapt to each team's Jira workflow.*
