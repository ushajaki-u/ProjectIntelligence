# Project Intelligence — Product Discovery & PRD

> **Working document:** This PRD will be developed incrementally using the seven-step product-discovery approach documented in the Codebasics Digital Asset Assistant capstone. Sections will be added and refined as discovery progresses. This document records the current understanding; it does not assume that the proposed solution or technology has already been validated.

## Product context

Project Intelligence is an exploration of how work-item data and external program information might be brought together to help a program/project manager understand and communicate the current delivery position across multiple projects.

**Current discovery status:** Initial current-state user journey documented from the product owner's personal experience. Other users' experiences and the broader problem hypothesis have not yet been validated.

## Codebasics capstone process

The following sequence will guide the work. We will complete and add each part incrementally rather than treating every deliverable as required upfront.

| # | Step | Status |
|---|---|---|
| 1 | Problem discovery & user research (persona, empathy map, 5 Whys, root cause) | In progress — initial user journey captured |
| 2 | AI opportunity mapping (user journey, opportunity map, architecture, risks) | Not started |
| 3 | Product requirements document (North Star, guardrails, evaluations, technology/model strategy as applicable) | Not started |
| 4 | Cost estimation | Not started |
| 5 | Working prototype | Not started |
| 6 | Stakeholder presentation | Not started |
| 7 | Stakeholder demo | Not started |

---

## Step 1 — Problem Discovery & User Research

### 1.1 Initial user context

The initial user perspective is based on the product owner's experience managing approximately five concurrent projects, with around 5–10 people per project. Teams are distributed across global locations.

The program/project manager needs to be able to understand and communicate where each project and team stands at a particular point in time, regardless of project size or execution approach.

This is an initial perspective, not yet a validated statement about all project managers.

### 1.2 Current user journey — before solution

|  | **1. Manage Multiple Projects** | **2. Collect Execution Updates** | **3. Gather Schedule & Milestone Information** |
|---|---|---|---|
| **Behavior** | Oversees multiple projects, teams and deliverables simultaneously. Needs visibility into where each team stands. | Uses daily team interactions, meetings and work-management systems such as Jira to understand progress, issues and blockers. | Retrieves project schedules from Excel or Microsoft Project (MPP). Collects milestones and commitments maintained in PowerPoint and Excel. |
| **Triggers** | Ongoing responsibility across multiple concurrent projects; management requests for current status. | Daily team coordination, progress reviews, emerging issues and requests for status updates. | Upcoming milestones, schedule reviews, planning changes and management reporting cycles. |
| **Pain** | No single consolidated view of all projects and their current delivery position. The project manager must assemble the picture across multiple teams. | Information is distributed across conversations and work-management systems. Actual blockers or risks may be discussed verbally but not reflected in Jira until they have escalated. System status may not reflect the current reality. | Critical program-level information is outside the work-management system. Schedules, milestones and commitments are maintained in separate files and presentations. |

|  | **4. Reconcile Changes & Delivery Status** | **5. Prepare Management Reporting** | **6. Keep Reporting Current** |
|---|---|---|---|
| **Behavior** | Compares actual execution against planned schedules and milestones. Incorporates changing requirements, scope, dates, dependencies and team updates. | Consolidates information from multiple sources and prepares PowerPoint presentations to communicate project and program status. | Repeats the collection, reconciliation and reporting process as new information becomes available. |
| **Triggers** | New requirements, scope changes, revised dates, emerging blockers and changes in delivery commitments. | Weekly or periodic reviews, leadership meetings, escalation discussions and milestone reviews. | Continuous changes in project execution, schedules, requirements and milestones. |
| **Pain** | Changes across requirements, schedules and milestones create repeated reconciliation work. Information can become inconsistent or outdated across sources. Identifying the actual delivery position requires significant manual effort and depends on timely updates from multiple people. | Preparing PowerPoint reports is time-consuming and repetitive. The project manager must manually consolidate, interpret and validate information before communicating status. | The reporting cycle never really ends. By the time a presentation is prepared, underlying information may already have changed. Maintaining an accurate view becomes a continuous manual exercise. |

### 1.3 Key problem insight — initial hypothesis

The challenge is not necessarily the absence of project information. It is the effort required to continuously bring fragmented, changing information together to understand and communicate the actual delivery position across multiple projects.

The project manager becomes the integration point between work-management systems, project schedules, milestone documents and information communicated by globally distributed teams.

### 1.4 Initial pain points observed

1. **Fragmented information:** Execution data, schedules and milestones live in different places.
2. **Delayed visibility:** What is happening in the team is not always reflected in the work-management system.
3. **Constant change:** Requirements, dates, milestones and priorities keep evolving.
4. **Manual reconciliation:** The project manager must compare and interpret information across several sources.
5. **Reporting overhead:** PowerPoint becomes a recurring manual activity, and the resulting snapshot can become outdated quickly.

### 1.5 Evidence and validation status

- **Source:** Product owner's direct experience as a program/project manager.
- **Observed context:** Approximately five concurrent projects, each with around 5–10 people, involving globally distributed teams.
- **Information sources described:** Work-management system (such as Jira), Excel schedules, Microsoft Project (MPP) files, PowerPoint milestone information, and daily team interactions.
- **Validation still needed:** Whether other program/project managers experience the same pain points, how frequently they occur, and which existing tools or organizational processes already address them.

These points are initial observations and hypotheses. They should not yet be presented as universal industry findings.

---

## Next sections — to be developed incrementally

- [ ] **Step 1 — Problem discovery & user research:** Persona, empathy map, 5 Whys and root-cause analysis.
- [ ] **Step 2 — Opportunity mapping:** Map user needs to possible capabilities; assess non-AI and AI approaches, architecture options and risks.
- [ ] **Step 3 — Product requirements:** Define the product direction, North Star, requirements, guardrails and evaluation approach.
- [ ] **Step 4 — Cost estimation:** Assess development, integration, infrastructure and licensing costs.
- [ ] **Step 5 — Working prototype:** Define and build a validated MVP.
- [ ] **Step 6 — Stakeholder presentation:** Communicate the problem, evidence, proposed approach and findings.
- [ ] **Step 7 — Stakeholder demo:** Demonstrate the prototype and capture feedback.

*This is a living discovery document. We will add one section at a time as we learn more. The current user journey and pain points are the only substantive discovery content captured so far.*
