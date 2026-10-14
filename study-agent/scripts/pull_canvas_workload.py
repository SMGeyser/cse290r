#!/usr/bin/env python3
"""Create a read-only JSON snapshot of a student's Canvas workload."""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="Start date (YYYY-MM-DD); defaults to today")
    parser.add_argument("--end", help="End date (YYYY-MM-DD); defaults to seven days from today")
    parser.add_argument("--output", default="canvas-workload.json", help="JSON output path")
    return parser.parse_args()


def validate_date(value, option):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"{option} must be YYYY-MM-DD.") from exc


def next_link(headers):
    for link in headers.get("Link", "").split(","):
        if 'rel="next"' in link:
            return link[link.find("<") + 1 : link.find(">")]
    return None


def assignment_is_relevant(assignment, start, end):
    """Keep work due this week and overdue work that has not been submitted."""
    due_at = assignment.get("due_at")
    if not due_at:
        return False
    try:
        due_date = datetime.fromisoformat(due_at.replace("Z", "+00:00")).date()
    except ValueError:
        return True  # Preserve an unexpected Canvas date for the planner to flag.
    if start <= due_date <= end:
        return True
    submission = assignment.get("submission") or {}
    completed = submission.get("workflow_state") in {"submitted", "graded"} or submission.get("excused")
    return due_date < start and not completed


class CanvasClient:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token

    def get_all(self, path, params=None):
        url = urljoin(self.base_url, "api/v1/" + path.lstrip("/"))
        if params:
            url += "?" + urlencode(params, doseq=True)
        records = []
        while url:
            request = Request(url, headers={"Authorization": f"Bearer {self.token}"})
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
                if not isinstance(payload, list):
                    raise RuntimeError(f"Expected a list from {url.split('?')[0]}.")
                records.extend(payload)
                url = next_link(response.headers)
        return records


def main():
    args = parse_args()
    today = date.today()
    start = validate_date(args.start, "--start") if args.start else today
    end = validate_date(args.end, "--end") if args.end else today + timedelta(days=7)
    if end < start:
        raise SystemExit("--end must not be before --start.")

    base_url = os.environ.get("CANVAS_BASE_URL")
    token = os.environ.get("CANVAS_API_TOKEN")
    if not base_url or not token:
        raise SystemExit("Set CANVAS_BASE_URL and CANVAS_API_TOKEN in the environment before running this helper.")

    client = CanvasClient(base_url, token)
    try:
        courses = client.get_all("users/self/courses", {"enrollment_state": "active", "per_page": 100})
        course_data = []
        for course in courses:
            course_id = course["id"]
            assignments = client.get_all(f"courses/{course_id}/assignments", {"per_page": 100, "include[]": "submission"})
            assignments = [item for item in assignments if assignment_is_relevant(item, start, end)]
            modules = client.get_all(f"courses/{course_id}/modules", {"per_page": 100, "include[]": "items"})
            course_data.append({"course": course, "assignments": assignments, "modules": modules})
        calendar = client.get_all("calendar_events", {"start_date": start.isoformat(), "end_date": end.isoformat(), "per_page": 100})
    except HTTPError as exc:
        raise SystemExit(f"Canvas request failed with HTTP {exc.code}. Check the base URL and token permissions.") from exc
    except URLError as exc:
        raise SystemExit(f"Could not reach Canvas: {exc.reason}") from exc

    snapshot = {
        "retrieved_at": datetime.now().astimezone().isoformat(),
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "courses": course_data,
        "calendar_events": calendar,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"Saved {len(course_data)} active course(s) and {len(calendar)} calendar event(s) to {output}.")


if __name__ == "__main__":
    main()
