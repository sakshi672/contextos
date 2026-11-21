"""Conservative, soft interpretations of common remembered search clues."""

import calendar
import re
from datetime import date, timedelta

MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if name})
_MONTH_PATTERN = "|".join(sorted(MONTHS, key=len, reverse=True))


def interpret(query: str, today: date | None = None) -> dict:
    today = today or date.today()
    lowered = query.lower()
    result = {}
    if re.search(r"\blast month\b", lowered):
        end = today.replace(day=1)
        start = (end - timedelta(days=1)).replace(day=1)
        result["approx_date"] = (start, end)
        result["date_label"] = "last month"
    elif re.search(r"\bthis month\b", lowered):
        start = today.replace(day=1)
        end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
        result["approx_date"] = (start, end)
        result["date_label"] = "this month"
    elif re.search(r"\blast week\b", lowered):
        result["approx_date"] = (today - timedelta(days=14), today - timedelta(days=7))
        result["date_label"] = "roughly last week"
    elif match := re.search(rf"\b({_MONTH_PATTERN})\s+(20\d{{2}})\b", lowered):
        month, year = MONTHS[match.group(1)], int(match.group(2))
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        result["approx_date"] = (start, end)
        result["date_label"] = start.strftime("%B %Y")
    domain = re.search(r"\b(?:from|on)\s+(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b", lowered)
    if domain:
        result["source_domain"] = domain.group(1)
    if re.search(r"\b(?:image|images|picture|pictures|screenshot|screenshots|photo|photos)\b", lowered):
        result["kind"] = "image"
    elif re.search(r"\b(?:pdf|paper)\b", lowered):
        result["kind"] = "pdf"
    return result


def reasons(row: dict, clues: dict, *, explicit_date: bool, explicit_domain: bool,
            explicit_kind: bool) -> list[str]:
    matched = []
    if "approx_date" in clues and not explicit_date:
        start, end = clues["approx_date"]
        if start <= row["captured_at"].date() < end:
            matched.append("approximate_date")
    if clues.get("source_domain") and not explicit_domain and row.get("source_domain") == clues["source_domain"]:
        matched.append("source_hint")
    if clues.get("kind") and not explicit_kind and row.get("kind") == clues["kind"]:
        matched.append("type_hint")
    return matched
