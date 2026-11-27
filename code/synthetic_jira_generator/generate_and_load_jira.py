"""Config-driven synthetic project generator and Jira Cloud loader.

Safe default: output.load_to_jira=false. The script always generates and validates
an Excel preview first. Jira creation is sequential so Jira parent keys can be
used when creating Stories, Bugs, and Subtasks.
"""

import json
import math
import random
import time
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from requests.auth import HTTPBasicAuth

CONFIG_FILE = Path(__file__).with_name("synthetic_project_config.json")


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def pct_count(total, percent):
    return max(0, min(total, round(total * percent / 100)))


def largest_remainder_counts(total, percentages):
    raw = {name: total * value / 100 for name, value in percentages.items()}
    counts = {name: math.floor(value) for name, value in raw.items()}
    remaining = total - sum(counts.values())
    order = sorted(raw, key=lambda name: (raw[name] - counts[name], name), reverse=True)
    for name in order[:remaining]:
        counts[name] += 1
    return counts


def load_config(path=CONFIG_FILE):
    with Path(path).open("r", encoding="utf-8") as file:
        config = json.load(file)
    validate_config(config)
    return config


def validate_percent(name, value):
    if not 0 <= value <= 100:
        raise ValueError(f"{name} must be between 0 and 100")


def validate_config(config):
    project = config["project"]
    start = parse_date(project["start_date"])
    end = parse_date(project["end_date"])
    snapshot = parse_date(project["snapshot_date"])
    if not start < end:
        raise ValueError("project.start_date must be before end_date")
    if not start <= snapshot <= end:
        raise ValueError("project.snapshot_date must be within project dates")
    if not config["teams"]:
        raise ValueError("At least one team is required")
    team_names = [team["name"] for team in config["teams"]]
    if len(team_names) != len(set(team_names)):
        raise ValueError("Team names must be unique")

    quarter_names = []
    previous_end = None
    for quarter in config["quarters"]:
        q_start = parse_date(quarter["start_date"])
        q_end = parse_date(quarter["end_date"])
        if not start <= q_start <= q_end <= end:
            raise ValueError(f"Quarter outside project dates: {quarter['name']}")
        if previous_end and q_start <= previous_end:
            raise ValueError("Quarters must be chronological and non-overlapping")
        previous_end = q_end
        quarter_names.append(quarter["name"])

    milestone_dates = []
    for milestone in config["milestones"]:
        value = parse_date(milestone["date"])
        if not start <= value <= end:
            raise ValueError(f"Milestone outside project: {milestone['name']}")
        if milestone["quarter"] not in quarter_names:
            raise ValueError(f"Unknown milestone quarter: {milestone['quarter']}")
        milestone_dates.append(value)
    if milestone_dates != sorted(milestone_dates):
        raise ValueError("Milestones must be chronological")

    for quarter in quarter_names:
        statuses = config["status_percentages"][quarter]
        if sum(statuses.values()) != 100:
            raise ValueError(f"Status percentages for {quarter} must total 100")
        for key, value in config["field_percentages"][quarter].items():
            validate_percent(f"field_percentages.{quarter}.{key}", value)
        validate_percent(f"past_due_percentages.{quarter}", config["past_due_percentages"][quarter])
    if sum(config["epic_priority_percentages"].values()) != 100:
        raise ValueError("Epic priority percentages must total 100")


def quarter_for_date(config, value):
    for quarter in config["quarters"]:
        if parse_date(quarter["start_date"]) <= value <= parse_date(quarter["end_date"]):
            return quarter
    raise ValueError(f"No quarter found for {value}")


def milestone_for_quarter(config, quarter_name):
    candidates = [
        item for item in config["milestones"]
        if item["quarter"] == quarter_name and item["name"] != "Final Demo"
    ]
    return candidates[0] if candidates else None


def random_date(rng, start, end):
    return start + timedelta(days=rng.randint(0, (end - start).days))


def create_base_rows(config):
    rng = random.Random(config["generator"]["random_seed"])
    counts = config["ticket_counts"]
    work_types = config["work_types"]
    rows = []
    sequence = 1

    def next_id(prefix):
        nonlocal sequence
        value = f"{prefix}-{sequence:05d}"
        sequence += 1
        return value

    teams = config["teams"]
    quarters = config["quarters"]
    current_quarter = config.get("current_quarter")
    for team in teams:
        for quarter in quarters:
            for _ in range(counts["epics_per_team_per_quarter"]):
                epic_id = next_id("EPIC")
                planned = random_date(
                    rng,
                    parse_date(quarter["start_date"]),
                    parse_date(quarter["end_date"]),
                )
                rows.append(new_row(config, epic_id, "", epic_id, 0, work_types["epic"], team, quarter, planned))

                # Cross-functional: one story per team under each epic.
                # Descendants keep the EPIC's quarter/label so the whole epic ships as one unit.
                for story_team in teams:
                    for _ in range(counts.get("stories_per_team", 1)):
                        story_id = next_id("STORY")
                        story_due = max(parse_date(quarter["start_date"]), planned - timedelta(days=rng.randint(0, 20)))
                        rows.append(new_row(config, story_id, epic_id, epic_id, 1, work_types["story"], story_team, quarter, story_due))
                        for _ in range(counts.get("subtasks_per_story", 0)):
                            child_id = next_id("SUBTASK")
                            child_due = max(parse_date(quarter["start_date"]), story_due - timedelta(days=rng.randint(0, 10)))
                            rows.append(new_row(config, child_id, story_id, epic_id, 2, work_types["subtask"], story_team, quarter, child_due))

                # Bugs only in the CURRENT quarter (you only get bugs on code already developed).
                if current_quarter is None or quarter["name"] == current_quarter:
                    for bug_team in teams:
                        for _ in range(counts.get("bugs_per_team", 1)):
                            bug_id = next_id("BUG")
                            bug_due = max(parse_date(quarter["start_date"]), planned - timedelta(days=rng.randint(0, 15)))
                            rows.append(new_row(config, bug_id, epic_id, epic_id, 1, work_types["bug"], bug_team, quarter, bug_due))
                            for _ in range(counts.get("subtasks_per_bug", 0)):
                                child_id = next_id("BUGSUB")
                                child_due = max(parse_date(quarter["start_date"]), bug_due - timedelta(days=rng.randint(0, 7)))
                                rows.append(new_row(config, child_id, bug_id, epic_id, 2, work_types["subtask"], bug_team, quarter, child_due))

    assign_statuses(config, rows, rng)
    assign_priorities(config, rows, rng)
    assign_schedule_fields(config, rows, rng)
    apply_past_due_rules(config, rows, rng)
    apply_test_cases(config, rows, rng)
    build_dependencies(config, rows, rng)
    validate_rows(config, rows)
    return rows


def new_row(config, synthetic_id, parent_id, epic_id, level, work_type, team, quarter, planned_due):
    milestone = milestone_for_quarter(config, quarter["name"])
    return {
        "Synthetic ID": synthetic_id,
        "Jira Key": "",
        "Parent Synthetic ID": parent_id,
        "Parent Jira Key": "",
        "Epic Synthetic ID": epic_id,
        "Hierarchy Level": level,
        "Work Type": work_type,
        "Summary": f"Synthetic {work_type} {synthetic_id}",
        "Delivery Team": team["name"],
        "Country": team["country"],
        "Quarter": quarter["name"],
        "Labels": quarter["label"],
        "Milestone": milestone["name"] if milestone else "",
        "Status": "",
        "Priority": "",
        "Actual Start": "",
        "Due Date": "",
        "Original Estimate Days": "",
        "Planned Due Date": planned_due.isoformat(),
        "Is Past Due": "No",
        "Dependency Target Synthetic ID": "",
        "Expected Test Scenario": "",
        "Reporter": config["jira"]["email"],
    }


def assign_statuses(config, rows, rng):
    by_quarter = defaultdict(list)
    for row in rows:
        by_quarter[row["Quarter"]].append(row)
    for quarter, items in by_quarter.items():
        shuffled = items[:]
        rng.shuffle(shuffled)
        counts = largest_remainder_counts(len(items), config["status_percentages"][quarter])
        cursor = 0
        for status, count in counts.items():
            for row in shuffled[cursor:cursor + count]:
                row["Status"] = status
            cursor += count


def assign_priorities(config, rows, rng):
    epics = [r for r in rows if r["Work Type"] == config["work_types"]["epic"]]
    shuffled = epics[:]
    rng.shuffle(shuffled)
    counts = largest_remainder_counts(len(epics), config["epic_priority_percentages"])
    cursor = 0
    for priority, count in counts.items():
        for row in shuffled[cursor:cursor + count]:
            row["Priority"] = priority
        cursor += count


def estimate_bounds(config, row):
    if row["Work Type"] == config["work_types"]["bug"]:
        return config["estimates"]["bug"]
    if row["Work Type"] == config["work_types"]["subtask"]:
        return config["estimates"]["subtask"]
    return None


def exact_selection(rng, items, percent):
    result = items[:]
    rng.shuffle(result)
    return set(row["Synthetic ID"] for row in result[:pct_count(len(items), percent)])


def assign_schedule_fields(config, rows, rng):
    by_quarter = defaultdict(list)
    for row in rows:
        by_quarter[row["Quarter"]].append(row)
    for quarter, items in by_quarter.items():
        fields = config["field_percentages"][quarter]
        with_start = exact_selection(rng, items, fields["has_actual_start"])
        with_due = exact_selection(rng, items, fields["has_due_date"])
        estimable = [r for r in items if estimate_bounds(config, r)]
        with_estimate = exact_selection(rng, estimable, fields["has_original_estimate"])
        for row in items:
            planned = parse_date(row["Planned Due Date"])
            bounds = estimate_bounds(config, row)
            estimate = rng.randint(bounds["minimum_days"], bounds["maximum_days"]) if bounds else ""
            if row["Synthetic ID"] in with_estimate:
                row["Original Estimate Days"] = estimate
            if row["Synthetic ID"] in with_due:
                row["Due Date"] = planned.isoformat()
            if row["Synthetic ID"] in with_start:
                duration = estimate if isinstance(estimate, int) else rng.randint(2, 20)
                row["Actual Start"] = (planned - timedelta(days=duration)).isoformat()


def apply_past_due_rules(config, rows, rng):
    snapshot = parse_date(config["project"]["snapshot_date"])
    for quarter in config["past_due_percentages"]:
        eligible = [
            r for r in rows
            if r["Quarter"] == quarter and r["Status"] not in {"Done", "Deprecated"}
        ]
        selected = exact_selection(rng, eligible, config["past_due_percentages"][quarter])
        for row in eligible:
            if row["Synthetic ID"] in selected:
                row["Due Date"] = (snapshot - timedelta(days=rng.randint(1, 30))).isoformat()
                row["Is Past Due"] = "Yes"


def apply_test_cases(config, rows, rng):
    test_cases = config["test_cases"]
    leaves = [
        r for r in rows
        if r["Work Type"] in {config["work_types"]["subtask"], config["work_types"]["bug"]}
    ]
    shuffled = leaves[:]
    rng.shuffle(shuffled)
    cursor = 0

    def take_one(name):
        nonlocal cursor
        if test_cases.get(name, 0) <= 0 or cursor >= len(shuffled):
            return None
        row = shuffled[cursor]
        cursor += 1
        return row

    row = take_one("missing_due_date")
    if row:
        row["Due Date"] = ""
        row["Expected Test Scenario"] = "Missing Due Date"
    row = take_one("missing_actual_start")
    if row:
        row["Actual Start"] = ""
        row["Expected Test Scenario"] = "Missing Actual Start"
    row = take_one("missing_estimate")
    if row:
        row["Original Estimate Days"] = ""
        row["Expected Test Scenario"] = "Missing Estimate"
    row = take_one("missing_delivery_team")
    if row:
        row["Delivery Team"] = ""
        row["Expected Test Scenario"] = "Missing Delivery Team"
    row = take_one("start_date_after_due_date")
    if row:
        if not row["Due Date"]:
            row["Due Date"] = row["Planned Due Date"]
        row["Actual Start"] = (parse_date(row["Due Date"]) + timedelta(days=3)).isoformat()
        row["Expected Test Scenario"] = "Start Date After Due Date"

    parents = [r for r in rows if r["Hierarchy Level"] < 2]
    children_by_parent = defaultdict(list)
    for item in rows:
        children_by_parent[item["Parent Synthetic ID"]].append(item)

    if test_cases.get("done_parent_with_active_child", 0) and parents:
        parent = parents[0]
        direct = children_by_parent[parent["Synthetic ID"]]
        if direct:
            parent["Status"] = "Done"
            direct[0]["Status"] = "In Progress"
            parent["Expected Test Scenario"] = "Done Parent With Active Child"

    if test_cases.get("active_parent_with_all_children_done", 0) and len(parents) > 1:
        parent = parents[1]
        direct = children_by_parent[parent["Synthetic ID"]]
        if direct:
            parent["Status"] = "In Progress"
            for child in direct:
                child["Status"] = "Done"
            parent["Expected Test Scenario"] = "Active Parent With All Children Done"


def build_dependencies(config, rows, rng):
    settings = config["dependencies"]
    if not settings["enabled"]:
        return
    epics = [r for r in rows if r["Work Type"] == config["work_types"]["epic"]]
    count = min(settings["number_of_epics_with_dependencies"], len(epics))
    selected = rng.sample(epics, count)
    for source, target in zip(selected, selected[1:]):
        source["Dependency Target Synthetic ID"] = target["Synthetic ID"]


def validate_rows(config, rows):
    ids = [r["Synthetic ID"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate Synthetic IDs")
    known = set(ids)
    teams = {team["name"] for team in config["teams"]}
    quarters = {q["name"] for q in config["quarters"]}
    for row in rows:
        if row["Parent Synthetic ID"] and row["Parent Synthetic ID"] not in known:
            raise ValueError(f"Unknown parent for {row['Synthetic ID']}")
        if row["Delivery Team"] and row["Delivery Team"] not in teams:
            raise ValueError(f"Unknown team for {row['Synthetic ID']}")
        if row["Quarter"] not in quarters:
            raise ValueError(f"Unknown quarter for {row['Synthetic ID']}")


def validation_summary(config, rows):
    output = []
    for quarter in [q["name"] for q in config["quarters"]]:
        items = [r for r in rows if r["Quarter"] == quarter]
        if not items:
            continue
        status_counts = Counter(r["Status"] for r in items)
        for status, requested in config["status_percentages"][quarter].items():
            actual = round(status_counts[status] * 100 / len(items), 1)
            output.append([quarter, "Status", status, requested, actual, status_counts[status], len(items)])
        checks = {
            "has_actual_start": sum(bool(r["Actual Start"]) for r in items),
            "has_due_date": sum(bool(r["Due Date"]) for r in items),
            "has_original_estimate": sum(r["Original Estimate Days"] != "" for r in items),
        }
        for field, count in checks.items():
            requested = config["field_percentages"][quarter][field]
            actual = round(count * 100 / len(items), 1)
            output.append([quarter, "Field", field, requested, actual, count, len(items)])
    return output


def export_excel(config, rows):
    output = Path(__file__).with_name(config["output"]["excel_file"])
    workbook = Workbook()
    work = workbook.active
    work.title = "Work_Items"
    headers = list(rows[0].keys())
    work.append(headers)
    for row in rows:
        work.append([row[h] for h in headers])

    milestones = workbook.create_sheet("Milestones")
    milestones.append(["Name", "Date", "Quarter", "Deliverable Count"])
    for item in config["milestones"]:
        milestones.append([item["name"], item["date"], item["quarter"], item["deliverable_count"]])

    teams = workbook.create_sheet("Teams")
    teams.append(["Team", "Country"])
    for team in config["teams"]:
        teams.append([team["name"], team["country"]])

    validation = workbook.create_sheet("Validation")
    validation.append(["Quarter", "Category", "Item", "Requested %", "Actual %", "Actual Count", "Population"])
    for row in validation_summary(config, rows):
        validation.append(row)

    for sheet in workbook.worksheets:
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="D9EAF7")

    workbook.save(output)
    check = load_workbook(output, read_only=True)
    check.close()
    return output


class JiraClient:
    def __init__(self, config):
        jira = config["jira"]
        self.config = config
        self.base_url = jira["base_url"].rstrip("/")
        self.auth = HTTPBasicAuth(jira["email"], jira["api_token"])
        self.timeout = jira.get("request_timeout_seconds", 60)
        self.pause = jira.get("pause_between_requests_seconds", 0)
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        self.fields_by_name = {}
        self.issue_types_by_name = {}

    def request(self, method, endpoint, **kwargs):
        response = self.session.request(method, f"{self.base_url}{endpoint}", timeout=self.timeout, **kwargs)
        if not response.ok:
            raise RuntimeError(f"Jira {method} {endpoint} failed: {response.status_code} {response.text[:1000]}")
        if self.pause:
            time.sleep(self.pause)
        return response.json() if response.text else {}

    def discover(self):
        fields = self.request("GET", "/rest/api/3/field")
        self.fields_by_name = {field["name"].strip().lower(): field["id"] for field in fields}
        project_key = self.config["jira"]["project_key"]
        types = self.request("GET", f"/rest/api/3/issue/createmeta/{project_key}/issuetypes")
        values = types.get("issueTypes", types.get("values", []))
        self.issue_types_by_name = {item["name"].strip().lower(): item["id"] for item in values}

    def field_id(self, display_name):
        normalized = display_name.strip().lower()
        if normalized in {"summary", "parent", "priority", "labels", "duedate", "due date"}:
            return {"due date": "duedate"}.get(normalized, normalized)
        return self.fields_by_name.get(normalized)

    def issue_type_id(self, name):
        value = self.issue_types_by_name.get(name.strip().lower())
        if not value:
            raise ValueError(f"Jira work type not found in project: {name}")
        return value

    def create_issue(self, row, parent_key=None):
        mapping = self.config["jira_fields"]
        fields = {
            "project": {"key": self.config["jira"]["project_key"]},
            "issuetype": {"id": self.issue_type_id(row["Work Type"])},
            "summary": row["Summary"],
            "labels": [row["Labels"]] if row["Labels"] else [],
        }
        if parent_key:
            fields["parent"] = {"key": parent_key}
        if row["Due Date"]:
            fields["duedate"] = row["Due Date"]
        if row["Priority"]:
            fields["priority"] = {"name": row["Priority"]}

        # Native Team field: set by the team's id (discovered at runtime). Skip if
        # this Jira has no Team field or we have no id for the team.
        team_field = self.fields_by_name.get("team")
        team_ids = {t["name"]: t.get("id") for t in self.config["teams"]}
        team_id = team_ids.get(row.get("Delivery Team"))
        if team_field and team_id:
            fields[team_field] = team_id

        # Optional custom fields (e.g., Actual Start) — skip gracefully if the field
        # does not exist in this Jira, instead of failing the whole load.
        for display_name, value in {mapping.get("actual_start"): row.get("Actual Start")}.items():
            if not display_name or not value:
                continue
            field_id = self.field_id(display_name)
            if field_id:
                fields[field_id] = value

        if row["Original Estimate Days"] != "":
            fields["timetracking"] = {"originalEstimate": f"{row['Original Estimate Days']}d"}

        created = self.request("POST", "/rest/api/3/issue", json={"fields": fields})
        return created["key"]

    def transition_to(self, jira_key, target_status):
        current = self.request("GET", f"/rest/api/3/issue/{jira_key}?fields=status")
        if current.get("fields", {}).get("status", {}).get("name", "").lower() == target_status.lower():
            return
        transitions = self.request("GET", f"/rest/api/3/issue/{jira_key}/transitions").get("transitions", [])
        match = next((t for t in transitions if t.get("to", {}).get("name", "").lower() == target_status.lower()), None)
        if not match:
            raise ValueError(f"No direct transition from current status to '{target_status}' for {jira_key}")
        self.request("POST", f"/rest/api/3/issue/{jira_key}/transitions", json={"transition": {"id": match["id"]}})

    def link_issues(self, source_key, target_key, link_type):
        payload = {
            "type": {"name": link_type},
            "inwardIssue": {"key": target_key},
            "outwardIssue": {"key": source_key},
        }
        self.request("POST", "/rest/api/3/issueLink", json=payload)


def load_rows_to_jira(config, rows):
    client = JiraClient(config)
    client.discover()
    mapping = {}
    failures = []
    ordered = sorted(rows, key=lambda r: (r["Hierarchy Level"], r["Synthetic ID"]))
    limit_epics = config["output"].get("load_limit_epics")
    if limit_epics:
        epic_ids = sorted(r["Synthetic ID"] for r in ordered if r["Hierarchy Level"] == 0)[:limit_epics]
        keep = set(epic_ids)
        ordered = [r for r in ordered if r["Epic Synthetic ID"] in keep]
        print(f"TEST MODE (load_limit_epics={limit_epics}): loading {len(ordered)} items (epic + descendants)")
    for row in ordered:
        try:
            parent_key = mapping.get(row["Parent Synthetic ID"]) if row["Parent Synthetic ID"] else None
            jira_key = client.create_issue(row, parent_key)
            row["Jira Key"] = jira_key
            row["Parent Jira Key"] = parent_key or ""
            mapping[row["Synthetic ID"]] = jira_key
            try:
                client.transition_to(jira_key, row["Status"])
            except Exception as error:
                failures.append({"synthetic_id": row["Synthetic ID"], "jira_key": jira_key, "stage": "transition", "error": str(error)})
            print(f"Created {row['Synthetic ID']} -> {jira_key}")
        except Exception as error:
            failures.append({"synthetic_id": row["Synthetic ID"], "stage": "create", "error": str(error)})
            print(f"FAILED {row['Synthetic ID']}: {error}")

    for row in rows:
        target = row["Dependency Target Synthetic ID"]
        if target and row["Synthetic ID"] in mapping and target in mapping:
            try:
                client.link_issues(mapping[row["Synthetic ID"]], mapping[target], config["dependencies"]["link_type"])
            except Exception as error:
                failures.append({"synthetic_id": row["Synthetic ID"], "stage": "link", "error": str(error)})

    mapping_file = Path(__file__).with_name(config["output"]["jira_mapping_file"])
    mapping_file.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    failed_file = Path(__file__).with_name(config["output"]["failed_items_file"])
    failed_file.write_text(json.dumps(failures, indent=2), encoding="utf-8")
    return mapping, failures


def main():
    config = load_config()
    rows = create_base_rows(config)
    print(f"Generated {len(rows)} synthetic work items")
    if config["output"]["generate_excel"]:
        workbook = export_excel(config, rows)
        print(f"Preview workbook: {workbook}")
    if config["output"]["load_to_jira"]:
        if "your-site.atlassian.net" in config["jira"]["base_url"] or "PASTE_API_TOKEN" in config["jira"]["api_token"]:
            raise ValueError("Update Jira URL, email, API token, and project key before enabling load_to_jira")
        mapping, failures = load_rows_to_jira(config, rows)
        print(f"Created in Jira: {len(mapping)}")
        print(f"Failures: {len(failures)}")
    else:
        print("Jira load skipped because output.load_to_jira=false")


if __name__ == "__main__":
    main()
