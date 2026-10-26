from __future__ import annotations

import re
from datetime import date, time, timedelta


MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def extract_date(text: str, today: date) -> date | None:
    lowered = text.lower().strip()

    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", lowered)
    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(1))
        except ValueError:
            pass

    if re.search(r"\btoday\b", lowered):
        return today
    if re.search(r"\btomorrow\b", lowered):
        return today + timedelta(days=1)

    weekday_match = re.search(
        r"\b(?:(next|this)\s+)?(" + "|".join(WEEKDAYS) + r")\b", lowered
    )
    if weekday_match:
        modifier, weekday_name = weekday_match.groups()
        target = WEEKDAYS[weekday_name]
        delta = (target - today.weekday()) % 7
        if modifier == "next" and delta == 0:
            delta = 7
        elif delta == 0 and not modifier:
            delta = 7
        return today + timedelta(days=delta)

    month_pattern = (
        r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b"
    )
    month_match = re.search(month_pattern, lowered)
    if month_match:
        month_name, day_text, year_text = month_match.groups()
        year = int(year_text) if year_text else today.year
        candidate = date(year, MONTHS[month_name], int(day_text))
        if candidate < today and not year_text:
            candidate = date(year + 1, MONTHS[month_name], int(day_text))
        return candidate

    day_month_pattern = (
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")"
        r"(?:\s+(20\d{2}))?\b"
    )
    day_month_match = re.search(day_month_pattern, lowered)
    if day_month_match:
        day_text, month_name, year_text = day_month_match.groups()
        year = int(year_text) if year_text else today.year
        candidate = date(year, MONTHS[month_name], int(day_text))
        if candidate < today and not year_text:
            candidate = date(year + 1, MONTHS[month_name], int(day_text))
        return candidate

    return None


def extract_time(text: str) -> time | None:
    lowered = text.lower()
    meridiem_match = re.search(
        r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", lowered
    )
    if meridiem_match:
        hour = int(meridiem_match.group(1))
        minute = int(meridiem_match.group(2) or 0)
        if not 1 <= hour <= 12 or not 0 <= minute <= 59:
            return None
        is_pm = meridiem_match.group(3).startswith("p")
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0
        return time(hour, minute)

    twenty_four_hour_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lowered)
    if twenty_four_hour_match:
        return time(int(twenty_four_hour_match.group(1)), int(twenty_four_hour_match.group(2)))

    return None


def is_affirmative(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    exact = {
        "yes",
        "yes please",
        "confirm",
        "confirmed",
        "book it",
        "go ahead",
        "sounds good",
        "that works",
        "please do",
    }
    return normalized in exact or normalized.startswith("yes " )


def is_negative(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized in {"no", "no thanks", "cancel", "not now", "never mind"}


def has_safety_red_flag(text: str) -> bool:
    lowered = text.lower()
    phrases = (
        "chest pain",
        "cannot breathe",
        "can't breathe",
        "difficulty breathing",
        "severe bleeding",
        "unconscious",
        "stroke",
        "suicidal",
    )
    return any(phrase in lowered for phrase in phrases)

