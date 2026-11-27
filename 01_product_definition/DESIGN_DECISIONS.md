# Project Pulse — Design Decisions & Scope

Project Pulse is deliberately a **deterministic, rule-based baseline** for program
delivery visibility. This document records the scope decisions behind that baseline —
what was built now, why, and where each decision is headed — so the boundaries are
intentional and transparent, not accidental.

Every date, status, and risk signal is governed by an explicit, numbered rule
(**17 date roll-up rules + 9 Epic-health rules = 26 governed rules**; see
[`BUSINESS_RULES.md`](../BUSINESS_RULES.md)). Thresholds and status names are
configurable; the rules stay constant.

> **Scale note:** Project Pulse is *designed for* large programs — dozens of
> interdependent teams and 10,000+ tickets. The current baseline is **validated on a
> 4-team, ~500-ticket pilot** using synthetic data. Where this document refers to
> larger scale, it means the target the design is built toward, not what the pilot ran on.

| # | Decision & why it matters | Built now (baseline) — and why | Planned direction |
|---|---|---|---|
| 1 | **Deterministic rules vs. AI/ML** — a transparent, auditable baseline leadership can trust before any model is introduced. | Deterministic only. A 26-rule foundation establishes explainable logic first; every output traces to a rule and a Jira field. | Layer in historical snapshots and ML/NLP once data-hygiene gates are proven. |
| 2 | **An alternative to raw Advanced Roadmaps / Gantt views** — surface buried blockers and missing dates directly, instead of digging through schedule visualizations. | Exception-first reporting. Rule filters highlight the items that need action (missing dates, blocked work, data issues) rather than dumping the whole schedule. | Keep executive reporting focused on critical exceptions, not raw schedule dumps. |
| 3 | **Intra-feature vs. cross-Epic dependencies** — upstream delays cascade horizontally across many interdependent teams. | Intra-feature only. Cross-team stories are modeled under a single Epic; inter-Epic links are excluded to validate the core roll-up math first. | Ingest Jira issue links to map cross-Epic critical paths and propagate upstream delays automatically. |
| 4 | **Scope creep vs. rolling-wave planning** — distinguish normal multi-quarter elaboration from unplanned mid-quarter additions. | Point-in-time snapshot. Future-quarter Epic additions are treated as normal rolling-wave planning; historical trend tracking is deferred. | Store periodic snapshots to measure net scope added inside committed quarters and detect churn. |
| 5 | **Target dates vs. story points** — keep cross-program reporting objective when story points aren't standardized across teams. | Dates only. Anchored on documented target dates and a minimum due-date coverage threshold; story points excluded. | Add flow metrics (throughput, historical cycle time) to cover teams without leaf-level due dates. |
| 6 | **Team / component slicing** — avoid alert fatigue on very large programs by giving each lead visibility into their own workstream. | Label-based filtering. Baseline queries scope by project and release labels, validated on the ~500-ticket pilot. | Add component/team filters in `config.json` so individual leads can self-serve their own hygiene audits. |
| 7 | **External schedules (MPP/Excel) & regional holidays** — align executive commitments and regional calendars with day-to-day Jira execution. | Partial. Regional holiday-proximity warnings are built; reconciliation with external schedules stays manual for now. | Automate variance checks between external MPP/Excel milestones and Jira dates, plus capacity-adjusted timelines. |
| 8 | **Systemic friction & anti-gaming signals** — catch tickets bouncing between statuses or defect clusters early. | Deferred. Behavioral/history checks need multi-snapshot state tracking, which the baseline does not yet capture. | Flag high-churn tickets and bug concentrations as early coaching indicators for PMs and leads. |

---

*Baseline validated on synthetic pilot data (4 teams, ~500 tickets). See
[`BUSINESS_RULES.md`](../BUSINESS_RULES.md) for the full rule set and
[`code/`](../code/) for the implementation.*
