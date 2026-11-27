import json
from datetime import datetime, timedelta
from pathlib import Path

import requests
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from requests.auth import HTTPBasicAuth
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


CONFIG_FILE = Path(__file__).with_name("config.json")

DEFAULT_OUTPUT_FILE = "project_forecast_report.xlsx"
DEFAULT_PPTX_FILE = "project_forecast_executive_summary.pptx"


def get_project_labels(config):
    """Return the configured project label(s) as a list of non-empty strings.

    Accepts either project.labels (a list) or project.label (a single string),
    so older single-label configs keep working.
    """
    project = config["project"]
    raw = project.get("labels", project.get("label"))
    if isinstance(raw, str):
        candidates = [raw]
    elif isinstance(raw, (list, tuple)):
        candidates = list(raw)
    else:
        candidates = []
    return [str(label).strip() for label in candidates if str(label).strip()]


def load_config(config_file=CONFIG_FILE):
    """Read and validate configuration."""
    config_path = Path(config_file)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path.resolve()}"
        )

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    required_sections = [
        "jira",
        "project",
        "query",
        "fields",
        "forecasting",
        "output",
    ]

    for section in required_sections:
        if section not in config:
            raise ValueError(f"Missing config section: {section}")

    for value in ["base_url", "email", "api_token"]:
        if not config["jira"].get(value):
            raise ValueError(f"Missing jira.{value} in config.json")

    for value in ["project_key", "delivery_date"]:
        if not config["project"].get(value):
            raise ValueError(f"Missing project.{value} in config.json")

    if not get_project_labels(config):
        raise ValueError(
            "Config must set project.labels (a non-empty list) or project.label (a string)"
        )

    required_forecasting_values = [
        "max_depth",
        "excluded_statuses",
        "orange_threshold_days",
        "red_threshold_days",
        "minimum_due_date_coverage_percent",
    ]
    required_health_values = ["enabled", "blocked_statuses", "backlog_statuses", "backlog_release_warning_days"]
    if "epic_health_check" not in config:
        raise ValueError("Missing config section: epic_health_check")
    for value in required_health_values:
        if value not in config["epic_health_check"]:
            raise ValueError(f"Missing epic_health_check.{value} in config.json")

    for value in required_forecasting_values:
        if value not in config["forecasting"]:
            raise ValueError(
                f"Missing forecasting.{value} in config.json"
            )

    datetime.strptime(
        config["project"]["delivery_date"],
        "%Y-%m-%d",
    )

    orange_days = config["forecasting"]["orange_threshold_days"]
    red_days = config["forecasting"]["red_threshold_days"]

    if orange_days < 0 or red_days < 0:
        raise ValueError("Forecast thresholds cannot be negative")

    if orange_days >= red_days:
        raise ValueError(
            "orange_threshold_days must be less than red_threshold_days"
        )

    coverage = config["forecasting"]["minimum_due_date_coverage_percent"]
    if coverage < 0 or coverage > 100:
        raise ValueError(
            "minimum_due_date_coverage_percent must be between 0 and 100"
        )

    holiday_cfg = config.get("holiday_warnings", {})
    if holiday_cfg:
        warning_days = int(holiday_cfg.get("warning_days", 14))
        if warning_days < 0:
            raise ValueError("holiday_warnings.warning_days cannot be negative")

        locations = config.get("locations", {})
        team_locations = config.get("team_locations", {})
        if not isinstance(locations, dict):
            raise ValueError("locations must be a JSON object")
        if not isinstance(team_locations, dict):
            raise ValueError("team_locations must be a JSON object")

        for location_code, location in locations.items():
            if not isinstance(location, dict):
                raise ValueError(f"locations.{location_code} must be an object")
            for holiday in location.get("holidays", []):
                if not holiday.get("name") or not holiday.get("date"):
                    raise ValueError(
                        f"Each holiday in locations.{location_code}.holidays requires name and date"
                    )
                datetime.strptime(holiday["date"], "%Y-%m-%d")

        unknown_locations = sorted({
            location_code
            for location_code in team_locations.values()
            if location_code not in locations
        })
        if unknown_locations:
            raise ValueError(
                "team_locations references undefined locations: "
                + ", ".join(unknown_locations)
            )

    return config

def jira_get(config, endpoint, params=None):
    """Make one authenticated Jira GET request."""
    jira = config["jira"]
    base_url = jira["base_url"].rstrip("/")

    response = requests.get(
        f"{base_url}{endpoint}",
        auth=HTTPBasicAuth(jira["email"], jira["api_token"]),
        headers={"Accept": "application/json"},
        params=params,
        timeout=60,
    )

    response.raise_for_status()
    return response.json()


def search_jira(config, jql):
    """Run JQL and retrieve every result page."""
    requested_fields = list(config["fields"])
    if not any(str(field).strip().lower() == "labels" for field in requested_fields):
        requested_fields.append("labels")
    fields = ",".join(requested_fields)
    max_results = config["query"].get("max_results", 100)
    issues = []
    next_page_token = None

    while True:
        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": fields,
        }

        if next_page_token:
            params["nextPageToken"] = next_page_token

        data = jira_get(
            config,
            "/rest/api/3/search/jql",
            params=params,
        )

        issues.extend(data.get("issues", []))
        next_page_token = data.get("nextPageToken")

        if not next_page_token:
            break

    return issues


def get_epics(config):
    """Retrieve all Epics matching the configured project and label(s).

    One or more labels may be configured. Epics carrying ANY of the configured
    labels are included (the labels are OR'd together in JQL).
    """
    project_key = config["project"]["project_key"]
    labels = get_project_labels(config)
    label_clause = " OR ".join(f'labels = "{label}"' for label in labels)

    # Status is intentionally not filtered. The Excel Data sheet must show
    # the complete hierarchy, including excluded statuses.
    jql = (
        f'project = "{project_key}" '
        f'AND issuetype = Epic '
        f'AND ({label_clause}) '
        f'ORDER BY key ASC'
    )

    return search_jira(config, jql)


def get_children(config, issue_key):
    """Retrieve every direct child regardless of status."""
    jql = f'parent = "{issue_key}" ORDER BY key ASC'
    return search_jira(config, jql)


def get_excluded_statuses(config):
    """Return normalized excluded statuses from configuration."""
    return {
        status.strip().lower()
        for status in config["forecasting"]["excluded_statuses"]
    }


def create_row(
    config,
    issue,
    parent_key,
    level,
    epic_key,
    query_timestamp,
):
    """Convert one Jira issue into the internal report structure."""
    fields = issue.get("fields", {})
    status = fields.get("status", {}).get("name", "Unknown")
    excluded_statuses = get_excluded_statuses(config)
    excluded = status.strip().lower() in excluded_statuses

    assignee = "Unassigned"
    if fields.get("assignee"):
        assignee = fields["assignee"].get(
            "displayName",
            "Unassigned",
        )

    components = ", ".join(
        component.get("name", "")
        for component in fields.get("components", [])
        if component.get("name")
    )

    return {
        "query_timestamp": query_timestamp,
        "epic_key": epic_key,
        "key": issue.get("key"),
        "parent_key": parent_key,
        "level": level,
        "issue_type": fields.get("issuetype", {}).get(
            "name",
            "Unknown",
        ),
        "summary": fields.get("summary", ""),
        "status": status,
        "assignee": assignee,
        "team_location": resolve_team_location(config, assignee),
        "components": components or "None",
        "labels": list(fields.get("labels") or []),
        "start_date": fields.get("startdate"),
        "documented_due_date": fields.get("duedate"),
        "calculated_due_date": None,
        "variance_to_delivery_days": None,
        "forecast_status": None,
        "forecast_color": None,
        "excluded_from_calculation": excluded,
        "exclusion_reason": status if excluded else "",
    }


def get_descendants(
    config,
    issue_key,
    epic_key,
    current_level,
    max_depth,
    query_timestamp,
    all_rows,
):
    """Retrieve descendants recursively while preserving hierarchy order."""
    if current_level > max_depth:
        return

    children = get_children(config, issue_key)

    for child in children:
        row = create_row(
            config=config,
            issue=child,
            parent_key=issue_key,
            level=current_level,
            epic_key=epic_key,
            query_timestamp=query_timestamp,
        )

        all_rows.append(row)

        issue_type = row["issue_type"].strip().lower()
        is_subtask = issue_type in {"sub-task", "subtask"}

        if not is_subtask and current_level < max_depth:
            get_descendants(
                config=config,
                issue_key=row["key"],
                epic_key=epic_key,
                current_level=current_level + 1,
                max_depth=max_depth,
                query_timestamp=query_timestamp,
                all_rows=all_rows,
            )


def get_project_data(config):
    """Retrieve all matching Epics and their descendants."""
    query_timestamp = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    max_depth = config["forecasting"]["max_depth"]
    all_rows = []
    epics = get_epics(config)

    for epic in epics:
        epic_key = epic["key"]

        epic_row = create_row(
            config=config,
            issue=epic,
            parent_key=None,
            level=0,
            epic_key=epic_key,
            query_timestamp=query_timestamp,
        )
        all_rows.append(epic_row)

        get_descendants(
            config=config,
            issue_key=epic_key,
            epic_key=epic_key,
            current_level=1,
            max_depth=max_depth,
            query_timestamp=query_timestamp,
            all_rows=all_rows,
        )

    return epics, all_rows, query_timestamp


def parse_date(value):
    """Convert YYYY-MM-DD text into a date."""
    if not value:
        return None

    return datetime.strptime(value, "%Y-%m-%d").date()


def calculate_dates_bottom_up(all_rows):
    """
    Calculate dates from leaves to Epics.

    Excluded rows remain visible in the Data sheet but return no date to their
    parents. Leaf calculated date equals documented due date. An active parent
    calculated date equals the maximum calculated date among active children.
    """
    rows_by_key = {
        row["key"]: row
        for row in all_rows
    }

    children_by_parent = {}

    for row in all_rows:
        parent_key = row["parent_key"]
        if parent_key:
            children_by_parent.setdefault(
                parent_key,
                [],
            ).append(row["key"])

    def calculate_one(issue_key):
        row = rows_by_key[issue_key]

        if row["excluded_from_calculation"]:
            row["calculated_due_date"] = None
            row["forecast_status"] = "Excluded from calculation"
            row["forecast_color"] = "Green"
            return None

        child_keys = children_by_parent.get(issue_key, [])

        if not child_keys:
            calculated_date = parse_date(
                row["documented_due_date"]
            )
        else:
            active_child_dates = []

            for child_key in child_keys:
                child_date = calculate_one(child_key)
                if child_date is not None:
                    active_child_dates.append(child_date)

            calculated_date = (
                max(active_child_dates)
                if active_child_dates
                else None
            )

        row["calculated_due_date"] = (
            calculated_date.isoformat()
            if calculated_date
            else None
        )

        return calculated_date

    epic_rows = [
        row
        for row in all_rows
        if row["parent_key"] is None
    ]

    for epic_row in epic_rows:
        calculate_one(epic_row["key"])


def classify_variance(config, variance_days):
    """Apply configurable forecast thresholds."""
    if variance_days is None:
        return "Insufficient Data", None

    orange_threshold = config["forecasting"][
        "orange_threshold_days"
    ]
    red_threshold = config["forecasting"][
        "red_threshold_days"
    ]

    if variance_days > red_threshold:
        return "Delayed - Critical", "Red"

    if variance_days > orange_threshold:
        return "Delayed - Warning", "Orange"

    if variance_days > 0:
        return "Delayed - Within Threshold", None

    if variance_days == 0:
        return "On Target", None

    return "Ahead", None


def calculate_epic_health(config, all_rows):
    """Calculate factual health indicators for every open Epic."""
    health_cfg = config["epic_health_check"]
    if not health_cfg.get("enabled", True):
        return
    excluded = get_excluded_statuses(config)
    blocked_statuses = {s.strip().lower() for s in health_cfg["blocked_statuses"]}
    backlog_statuses = {s.strip().lower() for s in health_cfg["backlog_statuses"]}
    warning_days = int(health_cfg["backlog_release_warning_days"])
    today = datetime.now().date()
    project_delivery = parse_date(config["project"]["delivery_date"])
    epic_rows = [r for r in all_rows if r["parent_key"] is None]
    for epic in epic_rows:
        epic_status = epic["status"].strip().lower()
        if epic_status in excluded:
            epic["health_status"] = "Not Applicable - Epic Closed or Excluded"
            epic["blocked_count"] = epic["backlog_count"] = 0
            epic["backlog_missing_due_date_count"] = epic["backlog_near_release_count"] = 0
            epic["other_active_status_count"] = 0
            continue
        descendants = [r for r in all_rows if r["epic_key"] == epic["key"] and r["key"] != epic["key"]]
        active = [r for r in descendants if r["status"].strip().lower() not in excluded]
        blocked = [r for r in active if r["status"].strip().lower() in blocked_statuses]
        backlog = [r for r in active if r["status"].strip().lower() in backlog_statuses]
        backlog_missing = [r for r in backlog if not r["documented_due_date"]]
        release_date = parse_date(epic["documented_due_date"]) or project_delivery
        days_to_release = (release_date - today).days if release_date else None
        near_release = backlog if days_to_release is not None and days_to_release <= warning_days else []
        known = blocked_statuses | backlog_statuses
        other_active = [r for r in active if r["status"].strip().lower() not in known]
        epic["blocked_count"] = len(blocked)
        epic["backlog_count"] = len(backlog)
        epic["backlog_missing_due_date_count"] = len(backlog_missing)
        epic["backlog_near_release_count"] = len(near_release)
        epic["other_active_status_count"] = len(other_active)
        signals=[]
        if blocked: signals.append(f"{len(blocked)} Blocked")
        if backlog_missing: signals.append(f"{len(backlog_missing)} Backlog without due date")
        if near_release: signals.append(f"{len(near_release)} Backlog within {warning_days} days of release")
        epic["health_status"] = "Attention Required - " + "; ".join(signals) if signals else "No Configured Health Signals"

def calculate_missing_descendant_labels(config, all_rows):
    """Flag descendants that do not carry any of the configured project labels."""
    expected_labels = {label.strip().lower() for label in get_project_labels(config)}
    expected_display = " | ".join(get_project_labels(config))

    epic_rows = [row for row in all_rows if row["parent_key"] is None]
    for epic in epic_rows:
        missing_ticket_keys = []
        descendants = [
            row for row in all_rows
            if row["epic_key"] == epic["key"]
            and row["key"] != epic["key"]
        ]

        for descendant in descendants:
            labels = descendant.get("labels") or []
            normalized_labels = {
                str(label).strip().lower()
                for label in labels
                if str(label).strip()
            }
            has_expected_label = bool(normalized_labels & expected_labels)
            descendant["phase_label_check"] = (
                "OK" if has_expected_label else f"Missing {expected_display}"
            )
            descendant["missing_phase_label"] = not has_expected_label
            if not has_expected_label:
                missing_ticket_keys.append(descendant["key"])

        epic["phase_label_check"] = "Root Epic"
        epic["missing_phase_label"] = False
        epic["missing_phase_label_count"] = len(missing_ticket_keys)
        epic["missing_phase_label_ticket_keys"] = missing_ticket_keys


def calculate_project_forecast(
    config,
    all_rows,
    epic_count,
    query_timestamp,
):
    """Calculate forecasts from available dates and report coverage separately."""
    project_delivery_date = parse_date(config["project"]["delivery_date"])
    minimum_coverage = config["forecasting"][
        "minimum_due_date_coverage_percent"
    ]
    active_rows = [
        row for row in all_rows
        if not row["excluded_from_calculation"]
    ]
    excluded_rows = [
        row for row in all_rows
        if row["excluded_from_calculation"]
    ]
    epic_rows = [row for row in all_rows if row["parent_key"] is None]
    eligible_epic_dates = []

    for epic in epic_rows:
        all_descendants = [
            row for row in all_rows
            if row["epic_key"] == epic["key"]
            and row["key"] != epic["key"]
        ]
        all_descendants_done = (
            bool(all_descendants)
            and all(
                row["status"].strip().lower() == "done"
                for row in all_descendants
            )
        )
        active_descendants_exist = any(
            row["status"].strip().lower()
            not in {"done", "deprecated"}
            for row in all_descendants
        )

        active_descendants = [
            row for row in active_rows
            if row["epic_key"] == epic["key"]
            and row["key"] != epic["key"]
        ]
        dated_descendants = [
            row for row in active_descendants
            if row["documented_due_date"]
        ]
        total_count = len(active_descendants)
        dated_count = len(dated_descendants)
        missing_count = total_count - dated_count
        coverage = (
            round((dated_count / total_count) * 100, 1)
            if total_count else 0.0
        )
        epic["active_descendant_count"] = total_count
        epic["dated_descendant_count"] = dated_count
        epic["missing_due_date_count"] = missing_count
        epic["due_date_coverage_percent"] = coverage
        epic["forecast_confidence"] = (
            "Low - Coverage Below Minimum"
            if coverage < minimum_coverage
            else "Meets Minimum Coverage"
        )

        documented = parse_date(epic["documented_due_date"])
        calculated = parse_date(epic["calculated_due_date"])

        epic_status_normalized = epic["status"].strip().lower()

        if epic_status_normalized == "done" and active_descendants_exist:
            epic["forecast_status"] = (
                "Data Issue - Epic is Done but active descendants exist"
            )
            epic["forecast_color"] = "Orange"
            epic["variance_to_delivery_days"] = None
        elif epic_status_normalized == "done":
            epic["forecast_status"] = "Excluded - Epic is Done"
            epic["forecast_color"] = "Green"
            epic["variance_to_delivery_days"] = None
        elif epic_status_normalized == "deprecated":
            epic["forecast_status"] = "Excluded - Epic is Deprecated"
            epic["forecast_color"] = "Green"
            epic["variance_to_delivery_days"] = None
        elif all_descendants_done:
            epic["forecast_status"] = (
                "Review Required - Epic is active but all descendants are Done; "
                "confirm whether the Epic should be closed or work is undocumented"
            )
            epic["forecast_color"] = "Orange"
            epic["variance_to_delivery_days"] = None
        elif not documented:
            epic["forecast_status"] = "Insufficient Data - Epic Due Date Missing"
            epic["forecast_color"] = None
            epic["variance_to_delivery_days"] = None
        elif calculated is None:
            epic["forecast_status"] = "Insufficient Data - No Calculated Date"
            epic["forecast_color"] = None
            epic["variance_to_delivery_days"] = None
        else:
            variance = (calculated - documented).days
            epic["variance_to_delivery_days"] = variance
            epic["forecast_status"], epic["forecast_color"] = (
                classify_variance(config, variance)
            )
            eligible_epic_dates.append(max(documented, calculated))

    # Child rows remain informational in the Data sheet.
    for row in all_rows:
        if row["parent_key"] is None:
            continue
        if row["excluded_from_calculation"]:
            row["forecast_status"] = "Excluded from calculation"
            row["forecast_color"] = "Green"
            row["variance_to_delivery_days"] = None
            continue
        calculated = parse_date(row["calculated_due_date"])
        documented = parse_date(row["documented_due_date"])
        if calculated and documented:
            variance = (calculated - documented).days
            row["variance_to_delivery_days"] = variance
            row["forecast_status"], row["forecast_color"] = (
                classify_variance(config, variance)
            )
        else:
            row["variance_to_delivery_days"] = None
            row["forecast_status"] = "Insufficient Data"
            row["forecast_color"] = None

    project_descendants = [
        row for row in active_rows
        if row["key"] != row["epic_key"]
    ]
    dated_project_descendants = [
        row for row in project_descendants
        if row["documented_due_date"]
    ]
    total_descendants = len(project_descendants)
    dated_descendants = len(dated_project_descendants)
    missing_descendants = total_descendants - dated_descendants
    project_coverage = (
        round((dated_descendants / total_descendants) * 100, 1)
        if total_descendants else 0.0
    )

    project_forecast_confidence = (
        "Low - Coverage Below Minimum"
        if project_coverage < minimum_coverage
        else "Meets Minimum Coverage"
    )

    if not eligible_epic_dates:
        maximum_variance = None
        calculated_project_date = None
        project_status = "Unavailable - No Usable Epic Forecast Dates"
        project_color = None
    else:
        calculated_project_date = max(
            [project_delivery_date] + eligible_epic_dates
        )
        maximum_variance = (
            calculated_project_date - project_delivery_date
        ).days
        project_status, project_color = classify_variance(
            config, maximum_variance
        )

    unique_keys = {row["key"] for row in all_rows}
    duplicate_count = len(all_rows) - len(unique_keys)
    missing_phase_label_rows = [
        row for row in all_rows
        if row.get("missing_phase_label", False)
    ]
    missing_phase_label_ticket_keys = [
        row["key"] for row in missing_phase_label_rows
    ]

    top_level_epics = [row for row in all_rows if row["parent_key"] is None]
    progress_epics = [row for row in top_level_epics if row["status"].strip().lower() != "deprecated"]
    done_epics = [row for row in progress_epics if row["status"].strip().lower() == "done"]
    epic_completion_percent = round((len(done_epics) / len(progress_epics)) * 100, 1) if progress_epics else 0.0

    holiday_warning = calculate_upcoming_holidays(config)

    return {
        "query_timestamp": query_timestamp,
        "project_key": config["project"]["project_key"],
        "label": " | ".join(get_project_labels(config)),
        "delivery_date": project_delivery_date.isoformat(),
        "tickets_analyzed_count": len(all_rows),
        "unique_ticket_count": len(unique_keys),
        "duplicate_ticket_count": duplicate_count,
        "epic_count": epic_count,
        "progress_epic_count": len(progress_epics),
        "done_epic_count": len(done_epics),
        "epic_completion_percent": epic_completion_percent,
        "active_work_item_count": len(active_rows),
        "excluded_work_item_count": len(excluded_rows),
        "missing_phase_label_count": len(missing_phase_label_rows),
        "missing_phase_label_ticket_keys": missing_phase_label_ticket_keys,
        "active_descendant_count": total_descendants,
        "descendants_with_due_date_count": dated_descendants,
        "missing_due_date_count": missing_descendants,
        "due_date_coverage_percent": project_coverage,
        "minimum_coverage_percent": minimum_coverage,
        "forecast_confidence": project_forecast_confidence,
        "maximum_epic_variance_days": maximum_variance,
        "calculated_project_date": (
            calculated_project_date.isoformat()
            if calculated_project_date else None
        ),
        "variance_days": maximum_variance,
        "status": project_status,
        "color": project_color,
        "holiday_warning": holiday_warning,
    }


def resolve_team_location(config, assignee):
    """Return the configured location code for an assignee."""
    team_locations = config.get("team_locations", {})
    if not assignee or assignee == "Unassigned":
        return "UNKNOWN"
    if assignee in team_locations:
        return team_locations[assignee]
    normalized = {str(name).strip().lower(): code for name, code in team_locations.items()}
    return normalized.get(str(assignee).strip().lower(), "UNKNOWN")


def calculate_upcoming_holidays(config, report_date=None):
    """Return configured holidays from report date through the warning window."""
    holiday_cfg = config.get("holiday_warnings", {})
    if not holiday_cfg.get("enabled", False):
        return {
            "warning_days": int(holiday_cfg.get("warning_days", 14)),
            "total_count": 0,
            "locations": [],
            "summary": "Holiday warnings disabled",
        }

    start_date = report_date or datetime.now().date()
    warning_days = int(holiday_cfg.get("warning_days", 14))
    end_date = start_date + timedelta(days=warning_days)
    locations = config.get("locations", {})
    team_locations = config.get("team_locations", {})
    active_location_codes = sorted(set(team_locations.values()))

    warnings = []
    for location_code in active_location_codes:
        location = locations.get(location_code, {})
        upcoming = []
        for holiday in location.get("holidays", []):
            holiday_date = parse_date(holiday.get("date"))
            if holiday_date and start_date <= holiday_date <= end_date:
                upcoming.append({
                    "name": holiday.get("name", "Holiday"),
                    "date": holiday_date.isoformat(),
                    "days_away": (holiday_date - start_date).days,
                })
        if upcoming:
            members = sorted(
                name for name, code in team_locations.items()
                if code == location_code
            )
            warnings.append({
                "location_code": location_code,
                "location_name": location.get("name", location_code),
                "team_member_count": len(members),
                "team_members": members,
                "holidays": sorted(upcoming, key=lambda item: item["date"]),
                "holiday_count": len(upcoming),
            })

    total_count = sum(item["holiday_count"] for item in warnings)
    if warnings:
        summary = " | ".join(
            f"{item['location_code']}: {item['holiday_count']}"
            for item in warnings
        )
    else:
        summary = f"No configured holidays in the next {warning_days} days"

    return {
        "warning_days": warning_days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_count": total_count,
        "locations": warnings,
        "summary": summary,
    }


def clean_excel_value(value):
    """Remove characters that are invalid in Excel XML."""
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    if value is None:
        return ""
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)
    return value


def apply_row_fill(worksheet, row_number, fill, font=None):
    for cell in worksheet[row_number]:
        cell.fill = fill
        if font is not None:
            cell.font = font


def save_excel(config, all_rows, forecast):
    """Create workbook with four-level outline grouping."""
    from openpyxl import load_workbook
    output_name = config["output"].get(
        "excel_file", DEFAULT_OUTPUT_FILE
    )
    output_file = Path(__file__).with_name(output_name)
    temporary_file = output_file.with_name(
        output_file.stem + "_temporary.xlsx"
    )

    workbook = Workbook()
    green_fill = PatternFill("solid", fgColor="C6EFCE")
    green_font = Font(color="006100")
    orange_fill = PatternFill("solid", fgColor="F4B183")
    orange_font = Font(color="7F6000", bold=True)
    red_fill = PatternFill("solid", fgColor="FFC7CE")
    red_font = Font(color="9C0006", bold=True)
    yellow_fill = PatternFill("solid", fgColor="FFF2CC")
    yellow_font = Font(color="7F6000", bold=True)
    header_font = Font(bold=True)

    data_sheet = workbook.active
    data_sheet.title = "Data"
    data_sheet.sheet_properties.outlinePr.summaryBelow = False
    data_sheet.sheet_properties.outlinePr.applyStyles = False

    # Business-readable hierarchy columns first; audit columns follow.
    headers = [
        "Hierarchy", "Status", "Summary", "Assignee", "Location", "Components",
        "Documented Due Date", "Calculated Due Date", "Forecast Status",
        "Issue Type", "Key", "Parent Key", "Level", "Epic Key",
        "Start Date", "Included in Calculation", "Exclusion Reason",
        "Variance Days", "Query Timestamp", "Project Key", "Label",
        "Delivery Date", "Issue Labels", "Phase 1 Label Check",
    ]
    data_sheet.append(headers)
    for cell in data_sheet[1]:
        cell.font = header_font

    for row in all_rows:
        values = [
            "    " * row["level"] + row["key"],
            row["status"], row["summary"], row["assignee"],
            row.get("team_location", "UNKNOWN"), row["components"],
            row["documented_due_date"] or "",
            row["calculated_due_date"] or "", row["forecast_status"] or "",
            row["issue_type"], row["key"], row["parent_key"] or "",
            row["level"], row["epic_key"], row["start_date"] or "",
            "No" if row["excluded_from_calculation"] else "Yes",
            row["exclusion_reason"] or "",
            row["variance_to_delivery_days"]
            if row["variance_to_delivery_days"] is not None else "",
            row["query_timestamp"], forecast["project_key"],
            forecast["label"], forecast["delivery_date"],
            ", ".join(row.get("labels") or []),
            row.get("phase_label_check", ""),
        ]
        data_sheet.append([clean_excel_value(v) for v in values])
        excel_row = data_sheet.max_row
        level = min(max(int(row["level"]), 0), 4)
        if level > 0:
            # Level 1-4 rows are nested under their nearest summary row.
            data_sheet.row_dimensions[excel_row].outlineLevel = level
            data_sheet.row_dimensions[excel_row].hidden = True
        if row["excluded_from_calculation"]:
            apply_row_fill(
                data_sheet, excel_row, green_fill, green_font
            )
        if row.get("missing_phase_label", False):
            label_check_cell = data_sheet.cell(
                row=excel_row,
                column=headers.index("Phase 1 Label Check") + 1,
            )
            label_check_cell.fill = yellow_fill
            label_check_cell.font = yellow_font

    # Show Excel outline controls and start at Epic-only bird's-eye view.
    data_sheet.sheet_view.showOutlineSymbols = True

    report_sheet = workbook.create_sheet("Final Report")
    report_sheet.append(["PROJECT HEALTH & FORECAST ENGINE"])
    report_sheet["A1"].font = header_font
    summary = [
        ("Project", forecast["project_key"]),
        ("Label", forecast["label"]),
        ("Query Timestamp", forecast["query_timestamp"]),
        ("Tickets Analyzed", forecast["tickets_analyzed_count"]),
        ("Unique Tickets", forecast["unique_ticket_count"]),
        ("Duplicate Tickets", forecast["duplicate_ticket_count"]),
        ("Configured Delivery Date", forecast["delivery_date"]),
        ("Maximum Eligible Epic Variance Days", forecast["maximum_epic_variance_days"]),
        ("Forecast Date (Available Data)", forecast["calculated_project_date"] or "Unavailable"),
        ("Project Status", forecast["status"]),
        ("Data Coverage Percent", forecast["due_date_coverage_percent"]),
        ("Forecast Confidence", forecast["forecast_confidence"]),
        ("Minimum Coverage Reference", forecast["minimum_coverage_percent"]),
        ("Active Missing Due Dates", forecast["missing_due_date_count"]),
        ("Excluded Status Items", forecast["excluded_work_item_count"]),
        ("Descendants Missing Phase 1 Label", forecast["missing_phase_label_count"]),
        ("Holiday Warning Window Days", forecast["holiday_warning"]["warning_days"]),
        ("Upcoming Holidays in Window", forecast["holiday_warning"]["total_count"]),
        ("Upcoming Holidays by Location", forecast["holiday_warning"]["summary"]),
    ]
    for label, value in summary:
        report_sheet.append([clean_excel_value(label), clean_excel_value(value)])

    if forecast["color"] == "Red":
        for row_number in range(2, 2 + len(summary)):
            apply_row_fill(report_sheet, row_number, red_fill, red_font)
    elif forecast["color"] == "Orange":
        for row_number in range(2, 2 + len(summary)):
            apply_row_fill(report_sheet, row_number, orange_fill, orange_font)

    report_sheet.append([])
    report_sheet.append(["UPCOMING HOLIDAY WARNINGS BY LOCATION"])
    report_sheet[report_sheet.max_row][0].font = header_font
    report_sheet.append(["Location", "Team Members", "Holiday", "Date", "Days Away"])
    for cell in report_sheet[report_sheet.max_row]:
        cell.font = header_font
    holiday_locations = forecast["holiday_warning"].get("locations", [])
    if holiday_locations:
        for location in holiday_locations:
            for holiday in location["holidays"]:
                report_sheet.append([
                    location["location_name"],
                    location["team_member_count"],
                    holiday["name"],
                    holiday["date"],
                    holiday["days_away"],
                ])
    else:
        report_sheet.append([forecast["holiday_warning"]["summary"]])

    report_sheet.append([])
    report_headers = [
        "Epic Key", "Epic Summary", "Forecast Status", "Epic Health Status",
        "Forecast Confidence", "Epic Documented Due Date",
        "Forecast Date (Available Data)", "Variance Days",
        "Active Descendants", "Descendants With Due Dates",
        "Active Missing Due Dates", "Due Date Coverage Percent",
        "Blocked Count", "Backlog Count", "Backlog Without Due Date",
        "Backlog Near Release", "Other Active Status Count",
        "Missing Phase 1 Labels", "Tickets Missing Phase 1 Label",
    ]
    report_sheet.append(report_headers)
    for cell in report_sheet[report_sheet.max_row]:
        cell.font = header_font

    for epic in [r for r in all_rows if r["parent_key"] is None]:
        values = [
            epic["key"], epic["summary"], epic["forecast_status"] or "",
            epic.get("health_status", ""),
            epic.get("forecast_confidence", ""),
            epic["documented_due_date"] or "",
            epic["calculated_due_date"] or "",
            epic["variance_to_delivery_days"]
            if epic["variance_to_delivery_days"] is not None else "",
            epic.get("active_descendant_count", 0),
            epic.get("dated_descendant_count", 0),
            epic.get("missing_due_date_count", 0),
            epic.get("due_date_coverage_percent", 0.0),
            epic.get("blocked_count", 0),
            epic.get("backlog_count", 0),
            epic.get("backlog_missing_due_date_count", 0),
            epic.get("backlog_near_release_count", 0),
            epic.get("other_active_status_count", 0),
            epic.get("missing_phase_label_count", 0),
            ", ".join(epic.get("missing_phase_label_ticket_keys", [])),
        ]
        report_sheet.append([clean_excel_value(v) for v in values])
        excel_row = report_sheet.max_row
        if epic["excluded_from_calculation"]:
            apply_row_fill(report_sheet, excel_row, green_fill, green_font)
        elif epic["forecast_color"] == "Red":
            apply_row_fill(report_sheet, excel_row, red_fill, red_font)
        elif epic["forecast_color"] == "Orange":
            apply_row_fill(report_sheet, excel_row, orange_fill, orange_font)

        if epic.get("missing_phase_label_count", 0) > 0:
            for column_name in (
                "Missing Phase 1 Labels",
                "Tickets Missing Phase 1 Label",
            ):
                cell = report_sheet.cell(
                    row=excel_row,
                    column=report_headers.index(column_name) + 1,
                )
                cell.fill = yellow_fill
                cell.font = yellow_font
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    workbook.save(temporary_file)
    check = load_workbook(temporary_file, read_only=False)
    check.close()
    if output_file.exists():
        output_file.unlink()
    temporary_file.replace(output_file)
    return output_file



def save_executive_powerpoint(config, all_rows, forecast):
    output_name = config["output"].get("pptx_file", DEFAULT_PPTX_FILE)
    output_file = Path(__file__).with_name(output_name)
    prs = Presentation(); prs.slide_width=Inches(13.333); prs.slide_height=Inches(7.5)
    navy=RGBColor(17,53,93); white=RGBColor(255,255,255); dark=RGBColor(31,31,31); gray=RGBColor(89,89,89)
    border=RGBColor(214,220,228); green=RGBColor(112,173,71); orange=RGBColor(237,125,49); red=RGBColor(192,0,0)
    light=RGBColor(242,244,247)
    # Lane 1 uses binary executive status: On Track or Not On Track.
    target_date = parse_date(forecast.get("delivery_date"))
    forecast_date = parse_date(forecast.get("calculated_project_date"))
    is_on_track = bool(target_date and forecast_date and forecast_date <= target_date)
    executive_status = "On Track" if is_on_track else "Not On Track"
    status_color = green if is_on_track else red

    def add_text(slide,text,x,y,w,h,size=16,bold=False,color=dark,align=PP_ALIGN.LEFT):
        box=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h)); tf=box.text_frame; tf.clear(); tf.vertical_anchor=MSO_ANCHOR.MIDDLE
        p=tf.paragraphs[0]; p.alignment=align; run=p.add_run(); run.text=str(text); run.font.name="Aptos"; run.font.size=Pt(size); run.font.bold=bold; run.font.color.rgb=color
        return box
    def add_card(slide,x,y,w,title,value,note,accent):
        sh=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(1.35)); sh.fill.solid(); sh.fill.fore_color.rgb=white; sh.line.color.rgb=border
        bar=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(.08),Inches(1.35)); bar.fill.solid(); bar.fill.fore_color.rgb=accent; bar.line.fill.background()
        add_text(slide,title.upper(),x+.18,y+.10,w-.30,.20,9,True,gray); add_text(slide,value,x+.18,y+.34,w-.30,.42,20,True,dark); add_text(slide,note,x+.18,y+1.01,w-.30,.22,8.5,False,gray)
    def d(v):
        if not v:return "Unavailable"
        try:return datetime.strptime(str(v),"%Y-%m-%d").strftime("%b %d, %Y")
        except:return str(v)
    def exception_color(n): return green if int(n or 0)==0 else red
    def forecast_color():
        f=parse_date(forecast.get("calculated_project_date")); t=parse_date(forecast.get("delivery_date"))
        if not f or not t:return navy
        if f<=t:return green
        days=(f-t).days
        if days<=config["forecasting"].get("orange_threshold_days",7):return orange
        return red

    excluded=get_excluded_statuses(config); hc=config["epic_health_check"]
    blocked_statuses={x.strip().lower() for x in hc["blocked_statuses"]}; backlog_statuses={x.strip().lower() for x in hc["backlog_statuses"]}
    active=[r for r in all_rows if r["status"].strip().lower() not in excluded]
    blocked=sum(1 for r in active if r["status"].strip().lower() in blocked_statuses)
    backlog=sum(1 for r in active if r["status"].strip().lower() in backlog_statuses)
    today=datetime.now().date(); past_due=0
    for r in active:
        x=parse_date(r.get("documented_due_date"))
        if x and x<today: past_due+=1
    target=parse_date(forecast.get("delivery_date")); days_to_target=(target-today).days if target else None
    near_release=days_to_target is not None and days_to_target<=hc.get("backlog_release_warning_days",14)
    backlog_accent=green if backlog==0 else (red if near_release else orange)

    # Slide 1
    slide=prs.slides.add_slide(prs.slide_layouts[6]); header=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,0,0,prs.slide_width,Inches(.94)); header.fill.solid(); header.fill.fore_color.rgb=navy; header.line.fill.background()
    add_text(slide,"PROJECT DELIVERY FORECAST",.42,.16,7.2,.34,24,True,white); add_text(slide,f"Project {forecast['project_key']} | Executive Summary",.43,.52,7.2,.22,10,False,RGBColor(218,230,242)); add_text(slide,f"Generated {forecast['query_timestamp']}",9.15,.29,3.7,.28,10,False,white,PP_ALIGN.RIGHT)
    add_text(slide,"Delivery outlook",.42,1.12,12.48,.32,17,True,navy)
    add_card(slide,.42,1.52,2.42,"Project Status",executive_status,"Forecast compared with target date",status_color)
    add_card(slide,2.96,1.52,2.12,"Today",datetime.now().strftime("%b %d, %Y"),"Report date",navy)
    add_card(slide,5.20,1.52,2.12,"Target Date",d(forecast.get("delivery_date")),"Committed delivery date",navy)
    add_card(slide,7.44,1.52,2.12,"Forecast Date",d(forecast.get("calculated_project_date")),"Based on available Jira dates",forecast_color())
    add_card(slide,9.68,1.52,3.23,"Epic Progress",f"{forecast.get('epic_completion_percent',0):.1f}%",f"{forecast.get('done_epic_count',0)} of {forecast.get('progress_epic_count',0)} Epics Done",green)
    add_text(slide,"Data quality and delivery checks",.42,3.34,12.48,.32,17,True,navy)
    # 5 compact cards
    cards=[("Missing Due Dates",forecast.get("missing_due_date_count",0),"Active tickets missing due dates",exception_color(forecast.get("missing_due_date_count",0))),
           ("Missing Phase Labels",forecast.get("missing_phase_label_count",0),"Descendants missing phase label",exception_color(forecast.get("missing_phase_label_count",0))),
           ("Blocked Tickets",blocked,"Active blocked tickets",exception_color(blocked)),
           ("Past Due Tickets",past_due,"Active tickets past due",exception_color(past_due)),
           ("Backlog Tickets",backlog,"Active backlog items",backlog_accent)]
    xs=[.42,2.94,5.46,7.98,10.50]
    for x,(title,val,note,accent) in zip(xs,cards): add_card(slide,x,3.74,2.31,title,str(val),note,accent)
    add_text(slide,"Green = healthy/no exception | Orange = warning | Red = action required | Navy = informational",.42,5.48,12.48,.24,9,False,gray)

    holiday_warning = forecast.get("holiday_warning", {})
    if holiday_warning.get("total_count", 0) > 0:
        holiday_parts = []
        for location in holiday_warning.get("locations", []):
            names = ", ".join(
                f"{holiday['name']} ({d(holiday['date'])})"
                for holiday in location["holidays"]
            )
            holiday_parts.append(
                f"{location['location_name']}: {names}"
            )
        holiday_text = (
            f"HOLIDAY WARNING - {holiday_warning['total_count']} holiday(s) in the next "
            f"{holiday_warning['warning_days']} days | " + " | ".join(holiday_parts)
        )
        banner=slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(.42), Inches(5.90),
            Inches(12.49), Inches(.60)
        )
        banner.fill.solid(); banner.fill.fore_color.rgb=RGBColor(255,242,204)
        banner.line.color.rgb=orange
        add_text(slide,holiday_text,.62,5.98,12.08,.40,10,True,RGBColor(127,96,0))
    else:
        add_text(
            slide, holiday_warning.get("summary", "No configured holidays in warning window"),
            .42,5.96,12.48,.24,9,False,gray
        )

    # Slide 2: only open Epics; each count uses active descendants only.
    slide=prs.slides.add_slide(prs.slide_layouts[6])
    header=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,0,0,prs.slide_width,Inches(.94))
    header.fill.solid(); header.fill.fore_color.rgb=navy; header.line.fill.background()
    add_text(slide,"OPEN EPIC FORECAST AND DELIVERY SIGNALS",.42,.16,9.0,.34,24,True,white)
    add_text(slide,f"Project {forecast['project_key']} | Active Epic Summary",.43,.52,7.2,.22,10,False,RGBColor(218,230,242))
    add_text(slide,f"Generated {forecast['query_timestamp']}",9.15,.29,3.7,.28,10,False,white,PP_ALIGN.RIGHT)

    open_epics=[
        row for row in all_rows
        if row["parent_key"] is None
        and row["status"].strip().lower() not in excluded
    ]
    epic_rows=[]
    expected_labels={lbl.strip().lower() for lbl in get_project_labels(config)}
    for epic in open_epics:
        active_descendants=[
            row for row in all_rows
            if row["epic_key"] == epic["key"]
            and row["key"] != epic["key"]
            and row["status"].strip().lower() not in excluded
        ]
        missing_labels=sum(
            1 for row in active_descendants
            if not ({
                str(label).strip().lower()
                for label in (row.get("labels") or [])
                if str(label).strip()
            } & expected_labels)
        )
        missing_dates=sum(1 for row in active_descendants if not row.get("documented_due_date"))
        past_due_count=0
        for row in active_descendants:
            due=parse_date(row.get("documented_due_date"))
            if due and due < today:
                past_due_count += 1
        blocked_count=sum(1 for row in active_descendants if row["status"].strip().lower() in blocked_statuses)
        backlog_count=sum(1 for row in active_descendants if row["status"].strip().lower() in backlog_statuses)
        epic_rows.append({
            "key":epic["key"], "summary":epic.get("summary", ""),
            "forecast":d(epic.get("calculated_due_date")),
            "variance":epic.get("variance_to_delivery_days"),
            "missing_labels":missing_labels, "past_due":past_due_count,
            "missing_dates":missing_dates, "blocked":blocked_count,
            "backlog":backlog_count,
        })

    # Prioritize open Epics with exceptions, then by forecast variance.
    epic_rows.sort(key=lambda item:(
        -(item["blocked"] + item["past_due"] + item["missing_dates"] + item["missing_labels"] + item["backlog"]),
        -(item["variance"] or 0), item["key"]
    ))
    epic_rows=epic_rows[:8]
    row_count=max(2,len(epic_rows)+1)
    shape=slide.shapes.add_table(row_count,9,Inches(.25),Inches(1.28),Inches(12.83),Inches(5.82))
    table=shape.table
    widths=[.82,3.05,1.12,.78,1.05,.90,1.12,.82,.82]
    for i,w in enumerate(widths): table.columns[i].width=Inches(w)
    headers=["Epic","Summary","Forecast","Variance","Missing Labels","Past Due","Missing Dates","Blocked","Backlog"]
    for c,h in enumerate(headers):
        cell=table.cell(0,c); cell.text=h; cell.fill.solid(); cell.fill.fore_color.rgb=navy
        p=cell.text_frame.paragraphs[0]; p.font.name="Aptos"; p.font.size=Pt(8.5); p.font.bold=True; p.font.color.rgb=white; p.alignment=PP_ALIGN.CENTER
    for rr,item in enumerate(epic_rows,1):
        variance=item["variance"]
        values=[item["key"],item["summary"],item["forecast"],"N/A" if variance is None else f"{variance:+d}",item["missing_labels"],item["past_due"],item["missing_dates"],item["blocked"],item["backlog"]]
        for c,v in enumerate(values):
            cell=table.cell(rr,c); cell.text=str(v); cell.fill.solid(); cell.fill.fore_color.rgb=white if rr%2 else light
            p=cell.text_frame.paragraphs[0]; p.font.name="Aptos"; p.font.size=Pt(8.5); p.font.color.rgb=dark
            p.alignment=PP_ALIGN.LEFT if c in (0,1,2) else PP_ALIGN.CENTER
            if c >= 4 and int(v or 0) > 0:
                cell.fill.fore_color.rgb=RGBColor(255,199,206); p.font.color.rgb=RGBColor(156,0,6); p.font.bold=True
    add_text(slide,"Only open Epics and active descendants are included. Done and Deprecated work is excluded.",.42,7.12,12.48,.22,9,False,gray)
    prs.save(output_file); return output_file

def print_forecast_report(forecast, output_file, pptx_file):
    print()
    print("=" * 72)
    print("PROJECT HEALTH & FORECAST ENGINE")
    print("=" * 72)
    print(f"Project                  : {forecast['project_key']}")
    print(f"Tickets Analyzed         : {forecast['tickets_analyzed_count']}")
    print(f"Unique Tickets           : {forecast['unique_ticket_count']}")
    print(f"Duplicate Tickets        : {forecast['duplicate_ticket_count']}")
    print(f"Missing Phase 1 Labels   : {forecast['missing_phase_label_count']}")
    print(f"Data Coverage            : {forecast['due_date_coverage_percent']}%")
    print(f"Coverage Reference       : {forecast['minimum_coverage_percent']}%")
    print(f"Forecast Confidence      : {forecast['forecast_confidence']}")
    print(f"Maximum Epic Variance    : {forecast['maximum_epic_variance_days']}")
    print(f"Forecast Date (Available Data): {forecast['calculated_project_date'] or 'Unavailable'}")
    print(f"Project Status           : {forecast['status']}")
    print(f"Excel Report             : {output_file}")
    print(f"Upcoming Holidays       : {forecast['holiday_warning']['summary']}")
    print(f"Executive PowerPoint     : {pptx_file}")
    print("=" * 72)


def main():
    config = load_config()

    print("1. Reading configuration...")
    print(
        f"   Project={config['project']['project_key']}, "
        f"Label={' | '.join(get_project_labels(config))}, "
        f"Delivery Date={config['project']['delivery_date']}"
    )

    print("2. Querying complete Epic hierarchy...")
    epics, all_rows, query_timestamp = get_project_data(config)
    print(
        f"   Retrieved {len(epics)} Epic(s) "
        f"and {len(all_rows)} total work item(s)."
    )

    print("3. Calculating dates bottom-up...")
    calculate_dates_bottom_up(all_rows)

    print("4. Calculating Epic health indicators...")
    calculate_epic_health(config, all_rows)

    print("5. Checking descendant labels...")
    calculate_missing_descendant_labels(config, all_rows)

    print("6. Applying forecast rules and exclusions...")
    forecast = calculate_project_forecast(
        config=config,
        all_rows=all_rows,
        epic_count=len(epics),
        query_timestamp=query_timestamp,
    )

    print("7. Creating two-sheet Excel report...")
    output_file = save_excel(
        config=config,
        all_rows=all_rows,
        forecast=forecast,
    )

    print("8. Creating executive PowerPoint...")
    pptx_file = save_executive_powerpoint(config, all_rows, forecast)

    print_forecast_report(
        forecast=forecast,
        output_file=output_file,
        pptx_file=pptx_file,
    )


if __name__ == "__main__":
    main()
