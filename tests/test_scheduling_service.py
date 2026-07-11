from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.core.booking import MeetingType
from app.core.scheduling import (
    BusyInterval,
    BusySource,
    RestrictionType,
    ScheduleRestriction,
    ScheduleSettings,
    SchedulingRuleError,
    SlotCalculationService,
    SlotExclusionReason,
    WorkingHoursRule,
)

NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
TARGET_DATE = date(2026, 7, 10)


def service() -> SlotCalculationService:
    return SlotCalculationService()


def consultation() -> MeetingType:
    return MeetingType(name="Консультация", allowed_durations_minutes=(30, 60, 90))


def diagnostics() -> MeetingType:
    return MeetingType(name="Диагностика", allowed_durations_minutes=(60,), is_fixed_duration=True)


def settings() -> ScheduleSettings:
    return ScheduleSettings(timezone="UTC")


def working_hours() -> list[WorkingHoursRule]:
    return [
        WorkingHoursRule(
            weekday=TARGET_DATE.weekday(),
            is_working_day=True,
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
    ]


def calculate(
    *,
    target_date: date = TARGET_DATE,
    meeting_type: MeetingType | None = None,
    duration_minutes: int | None = 60,
    restrictions: list[ScheduleRestriction] | None = None,
    busy_intervals: list[BusyInterval] | None = None,
):
    return service().calculate_slots(
        target_date=target_date,
        meeting_type=meeting_type or consultation(),
        duration_minutes=duration_minutes,
        now=NOW,
        settings=settings(),
        working_hours=working_hours(),
        restrictions=restrictions or [],
        busy_intervals=busy_intervals or [],
    )


def test_slots_do_not_appear_before_next_calendar_day() -> None:
    result = calculate(target_date=NOW.date())

    assert result.slots == []
    assert result.exclusion_counts[SlotExclusionReason.OUT_OF_BOOKING_RANGE] == 1


def test_slots_do_not_exceed_booking_horizon() -> None:
    result = calculate(target_date=NOW.date() + timedelta(days=31))

    assert result.slots == []
    assert result.exclusion_counts[SlotExclusionReason.OUT_OF_BOOKING_RANGE] == 1


def test_slots_stay_inside_working_hours_with_60_minute_step() -> None:
    result = calculate(duration_minutes=60)

    assert [slot.starts_at.time() for slot in result.slots] == [
        time(10, 0),
        time(11, 0),
        time(12, 0),
        time(13, 0),
    ]


def test_closed_day_returns_no_slots() -> None:
    result = calculate(
        restrictions=[
            ScheduleRestriction(
                restriction_date=TARGET_DATE,
                restriction_type=RestrictionType.CLOSED_DAY,
            )
        ]
    )

    assert result.slots == []
    assert result.exclusion_counts[SlotExclusionReason.CLOSED_DAY] == 1


def test_manual_interval_blocks_overlapping_slots() -> None:
    result = calculate(
        restrictions=[
            ScheduleRestriction(
                restriction_date=TARGET_DATE,
                restriction_type=RestrictionType.TIME_INTERVAL,
                start_time=time(11, 0),
                end_time=time(12, 0),
            )
        ]
    )

    blocked_starts = {time(11, 0)}

    assert all(slot.starts_at.time() not in blocked_starts for slot in result.slots)
    assert result.exclusion_counts[SlotExclusionReason.MANUAL_RESTRICTION] == 1


def test_calendar_busy_interval_uses_buffer_without_exposing_details() -> None:
    result = calculate(
        busy_intervals=[
            BusyInterval(
                starts_at=datetime(2026, 7, 10, 11, 0, tzinfo=UTC),
                ends_at=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
                source=BusySource.CALENDAR,
            )
        ]
    )

    assert result.slots == []
    assert result.exclusion_counts == {SlotExclusionReason.CALENDAR_BUSY: 4}


def test_active_reservation_blocks_slots() -> None:
    result = calculate(
        busy_intervals=[
            BusyInterval(
                starts_at=datetime(2026, 7, 10, 13, 0, tzinfo=UTC),
                ends_at=datetime(2026, 7, 10, 14, 0, tzinfo=UTC),
                source=BusySource.RESERVATION,
            )
        ]
    )

    assert result.exclusion_counts[SlotExclusionReason.ACTIVE_RESERVATION] == 3


def test_diagnostics_duration_is_fixed_to_60_minutes() -> None:
    result = calculate(meeting_type=diagnostics(), duration_minutes=None)

    assert result.slots[0].ends_at - result.slots[0].starts_at == timedelta(minutes=60)


def test_diagnostics_rejects_non_fixed_duration() -> None:
    with pytest.raises(SchedulingRuleError) as error:
        calculate(meeting_type=diagnostics(), duration_minutes=30)

    assert error.value.rule == "invalid_duration"


def test_consultation_accepts_30_60_90_minutes() -> None:
    assert calculate(duration_minutes=30).slots
    assert calculate(duration_minutes=60).slots
    assert calculate(duration_minutes=90).slots
