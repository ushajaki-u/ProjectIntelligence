# Project Intelligence

### From work-item data to program-level delivery intelligence

**Are we going to make the date?**

Large programs generate enormous amounts of work-item data. Turning that
data into a reliable delivery forecast still requires significant manual
effort.

Project Intelligence is a program-level intelligence layer built on top
of Jira and, eventually, other work management systems. It combines
work-item data with external program context to make delivery
forecasting, data-quality checks, and executive reporting easier.

**Project Intelligence goes beyond displaying project status. It analyzes
work-item data and program context to surface delivery risks, data gaps,
and forecast insights that may otherwise remain hidden across teams.**

*An applied data science project grounded in real program-delivery
challenges.*

![The complexity of modern program
delivery](images/complexity-infographic.png)

## What it does

  -----------------------------------------------------------------------
  Capability                          What it answers
  ----------------------------------- -----------------------------------
  **Delivery forecasting**            Are we likely to meet the target
                                      date?

  **Data quality & planning           Can we trust the work-item data?
  integrity**

  **Epic health**                     What active work, blockers, or
                                      planning gaps need attention?
  -----------------------------------------------------------------------

**Data quality is part of the answer---not an afterthought.**

A parent marked Done while its children remain active, missing or
overdue due dates, and inconsistent status/date information can distort
a forecast. Project Intelligence surfaces these issues rather than
blindly trusting the hierarchy.

## How it works

![Inside the Delivery Forecast Engine](images/how-it-works.svg)

Project Intelligence combines two sources:

-   **Work management system (currently Jira):** work items, hierarchy,
    status, ownership, and due dates.
-   **External program configuration:** program dates, milestones,
    holidays, team calendars, availability, and forecasting parameters.

The deterministic engine validates the data, applies configurable
business rules, and produces explainable program-level insights.

## What it produces today

-   **Excel audit trail:** work-item hierarchy, documented and
    calculated dates, forecast status, and data-quality findings.
-   **Executive PowerPoint:** program forecast, target-date comparison,
    Epic health, and exceptions requiring attention.

## Why deterministic first?

Start with transparent, testable business rules. Explore AI/ML only when
sufficient historical data is available to support better predictions.

See [Business Rules](./BUSINESS_RULES.md) for the current forecasting
and Epic-health rules.

## Capability roadmap

  Capability                           Status
  ------------------------------------ ---------
  Jira integration and core forecast   Built
  Data-quality checks                  Built
  Team and location mapping            Built
  Calendar adjustments                 Partial
  Dependency and capacity awareness    Planned
  Predictive delivery intelligence     Future

## Dependencies & limitations

The current implementation relies on Jira as its work-item data source.
Forecast quality depends on the completeness and accuracy of that data.
API availability, access permissions, and changes to the underlying
platform can affect the integration.

Supporting other work management systems will require additional
connectors and validation against each system's data model.

------------------------------------------------------------------------

**Project Intelligence doesn't replace the system that manages the work.
It makes the data in that system more useful for program-level
decisions.**
