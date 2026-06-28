"""Unit tests for the compliance due/status engine."""

from datetime import date

import pytest

from app.engine import (
    DAYS_PER_MONTH,
    IntervalKind,
    ItemTiming,
    Status,
    add_calendar_months,
    compute_status,
    utilisation_rate_per_day,
    worst,
)


# --- Calendar month math -----------------------------------------------------


def test_add_calendar_months_end_of_month_rule():
    # 24-month check done mid-June 2026 -> good through end of June 2028.
    assert add_calendar_months(date(2026, 6, 15), 24) == date(2028, 6, 30)


def test_add_calendar_months_rolls_year_and_short_month():
    # 12 months from Feb -> end of next Feb (handles 28/29 days).
    assert add_calendar_months(date(2026, 2, 10), 12) == date(2027, 2, 28)
    assert add_calendar_months(date(2027, 2, 10), 12) == date(2028, 2, 29)  # leap


def test_add_calendar_months_first_day_still_end_of_month():
    assert add_calendar_months(date(2026, 1, 1), 1) == date(2026, 2, 28)


# --- Calendar item status ----------------------------------------------------


def test_calendar_ok_due_soon_overdue():
    timing = ItemTiming(
        interval_kind=IntervalKind.CALENDAR,
        interval_months=12,
        last_done_date=date(2025, 7, 15),  # due through end of Jul 2026
        warning_days=30,
    )
    # Plenty of time
    r = compute_status(timing, today=date(2026, 1, 1))
    assert r.status == Status.OK
    assert r.next_due_date == date(2026, 7, 31)

    # Within warning window
    r = compute_status(timing, today=date(2026, 7, 20))
    assert r.status == Status.DUE_SOON

    # Past due
    r = compute_status(timing, today=date(2026, 8, 5))
    assert r.status == Status.OVERDUE
    assert r.remaining_days < 0


def test_calendar_unknown_without_last_done():
    timing = ItemTiming(interval_kind=IntervalKind.CALENDAR, interval_months=12)
    r = compute_status(timing, today=date(2026, 6, 1))
    assert r.status == Status.UNKNOWN


# --- Fixed expiry ------------------------------------------------------------


def test_fixed_expiry():
    timing = ItemTiming(
        interval_kind=IntervalKind.FIXED,
        fixed_expiry_date=date(2026, 7, 10),
        warning_days=30,
    )
    assert compute_status(timing, today=date(2026, 5, 1)).status == Status.OK
    assert compute_status(timing, today=date(2026, 6, 20)).status == Status.DUE_SOON
    assert compute_status(timing, today=date(2026, 8, 1)).status == Status.OVERDUE


# --- Hours item + projection -------------------------------------------------


def test_hours_remaining_and_projection():
    # Oil change every 50h, last done at 1200h. Now at 1235h -> 15h remain.
    timing = ItemTiming(
        interval_kind=IntervalKind.HOURS,
        interval_hours=50,
        last_done_hours=1200.0,
        warning_days=30,
    )
    rate = 1.0  # 1 hour/day -> 15 days to go
    r = compute_status(
        timing, today=date(2026, 6, 28), current_hours=1235.0, hours_rate_per_day=rate
    )
    assert r.next_due_hours == 1250.0
    assert r.remaining_hours == 15.0
    assert r.projected_due_date == date(2026, 7, 13)
    assert r.status == Status.DUE_SOON  # within 30 days


def test_hours_overdue_when_exceeded():
    timing = ItemTiming(
        interval_kind=IntervalKind.HOURS, interval_hours=50, last_done_hours=1200.0
    )
    r = compute_status(timing, today=date(2026, 6, 28), current_hours=1255.0,
                       hours_rate_per_day=1.0)
    assert r.remaining_hours == -5.0
    assert r.status == Status.OVERDUE


def test_hours_warning_hours_trigger():
    # Far out by date but close by hours -> DUE_SOON via warning_hours.
    timing = ItemTiming(
        interval_kind=IntervalKind.HOURS,
        interval_hours=50,
        last_done_hours=1200.0,
        warning_days=7,
        warning_hours=10,
    )
    r = compute_status(timing, today=date(2026, 6, 28), current_hours=1245.0,
                       hours_rate_per_day=0.1)  # slow rate => far projected date
    assert r.remaining_hours == 5.0
    assert r.status == Status.DUE_SOON


# --- Combo: whichever comes first --------------------------------------------


def test_combo_first_calendar_wins():
    # 50h or 4 months, whichever first. Calendar comes first here.
    timing = ItemTiming(
        interval_kind=IntervalKind.COMBO_FIRST,
        interval_hours=50,
        interval_months=4,
        last_done_hours=1200.0,
        last_done_date=date(2026, 3, 1),  # cal due end of Jul 2026
        warning_days=30,
    )
    r = compute_status(timing, today=date(2026, 6, 28), current_hours=1235.0,
                       hours_rate_per_day=0.83)
    # Calendar due 2026-07-31; hours projected ~ +18 days = 2026-07-16.
    # Earliest drives effective date.
    assert r.effective_due_date == date(2026, 7, 16)
    assert r.status == Status.DUE_SOON


def test_combo_first_status_is_worst():
    # Calendar overdue even though hours fine -> overall OVERDUE.
    timing = ItemTiming(
        interval_kind=IntervalKind.COMBO_FIRST,
        interval_hours=50,
        interval_months=4,
        last_done_hours=1200.0,
        last_done_date=date(2025, 1, 1),  # long overdue on calendar
        warning_days=30,
    )
    r = compute_status(timing, today=date(2026, 6, 28), current_hours=1205.0,
                       hours_rate_per_day=1.0)
    assert r.status == Status.OVERDUE


def test_combo_last_waits_for_latest():
    # 50h or 4 months whichever LAST: calendar passed but hours remain -> not yet due.
    timing = ItemTiming(
        interval_kind=IntervalKind.COMBO_LAST,
        interval_hours=50,
        interval_months=4,
        last_done_hours=1200.0,
        last_done_date=date(2025, 1, 1),  # calendar long past
        warning_days=30,
    )
    r = compute_status(timing, today=date(2026, 6, 28), current_hours=1205.0,
                       hours_rate_per_day=0.1)  # 45h left, slow -> far future
    assert r.status == Status.OK


# --- Utilisation rate --------------------------------------------------------


def test_utilisation_rate_from_history():
    readings = [
        (date(2026, 1, 1), 1000.0),
        (date(2026, 2, 1), 1031.0),  # ~31 days, 31 hours -> ~1.0/day
    ]
    rate = utilisation_rate_per_day(readings)
    assert rate == pytest.approx(1.0, abs=0.01)


def test_utilisation_rate_fallback_without_history():
    rate = utilisation_rate_per_day([], default_per_month=30.4368)
    assert rate == pytest.approx(1.0, abs=0.001)


def test_utilisation_rate_fallback_on_flat_or_negative():
    readings = [(date(2026, 1, 1), 1000.0), (date(2026, 2, 1), 1000.0)]
    rate = utilisation_rate_per_day(readings, default_per_month=DAYS_PER_MONTH)
    assert rate == pytest.approx(1.0, abs=0.001)  # falls back, not 0


# --- helpers -----------------------------------------------------------------


def test_worst_severity_order():
    assert worst(Status.OK, Status.OVERDUE, Status.DUE_SOON) == Status.OVERDUE
    assert worst(Status.OK, Status.UNKNOWN) == Status.OK
