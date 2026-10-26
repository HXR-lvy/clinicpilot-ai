from datetime import date, time

from app.temporal import extract_date, extract_time, is_affirmative, is_negative


TODAY = date(2026, 10, 26)


def test_relative_date_and_time_extraction():
    assert extract_date("next Friday", TODAY) == date(2026, 10, 30)
    assert extract_date("November 20, 2026", TODAY) == date(2026, 11, 20)
    assert extract_time("Can we do 10:30 AM?") == time(10, 30)
    assert extract_time("at 14:45") == time(14, 45)


def test_confirmation_phrases():
    assert is_affirmative("Yes, please")
    assert is_affirmative("confirm")
    assert is_negative("No thanks")
    assert not is_negative("notable symptom")

