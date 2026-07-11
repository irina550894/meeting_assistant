from datetime import date, time

from app.core.booking import BookingStatus
from app.integrations.telegram.admin_router import _parse_meeting_type_durations, _schedule_text
from app.integrations.telegram.local_memory import InMemoryRuntimeStore
from app.integrations.telegram.ports import AdminScheduleSettings, AdminWorkingHoursRule
from app.integrations.telegram.status_labels import booking_status_label
from app.settings.config import Settings


def test_schedule_text_shows_settings_and_working_hours() -> None:
    store = InMemoryRuntimeStore(Settings())

    settings = store.settings
    text = _schedule_text(
        settings=AdminScheduleSettings(
            timezone=settings.app_timezone,
            min_booking_lead_days=settings.min_booking_lead_days,
            booking_horizon_days=settings.booking_horizon_days,
            slot_step_minutes=settings.slot_step_minutes,
            meeting_buffer_minutes=settings.meeting_buffer_minutes,
        ),
        working_hours=[
            AdminWorkingHoursRule(
                weekday=0,
                is_working_day=True,
                start_time=time(10, 0),
                end_time=time(18, 0),
            )
        ],
    )

    assert "Расписание:" in text
    assert "Europe/Moscow" in text
    assert "Шаг слотов: 60 мин." in text
    assert "Пн: 10:00-18:00" in text


async def test_in_memory_admin_settings_manage_restrictions_and_meeting_types() -> None:
    store = InMemoryRuntimeStore(Settings())
    target_date = date(2026, 7, 13)

    await store.add_closed_day_restriction(
        restriction_date=target_date,
        admin_comment="manual",
    )
    restrictions = await store.list_upcoming_restrictions(from_date=date(2026, 7, 11))

    assert len(restrictions) == 1
    assert restrictions[0].restriction_date == target_date

    meeting_types = await store.list_meeting_types_admin()
    assert any(item.is_active for item in meeting_types)

    updated = await store.set_meeting_type_active(meeting_types[0].id, is_active=False)
    assert updated is True
    updated_meeting_types = await store.list_meeting_types_admin()
    assert updated_meeting_types[0].is_active is False

    added = await store.add_meeting_type(
        name="Разбор проекта",
        allowed_durations_minutes=(60, 90),
        is_fixed_duration=False,
    )
    assert added is not None
    assert added.name == "Разбор проекта"
    assert added.allowed_durations_minutes == (60, 90)


def test_admin_meeting_type_durations_parser() -> None:
    assert _parse_meeting_type_durations("90, 30, 60, 60") == (30, 60, 90)
    assert _parse_meeting_type_durations("120") is None
    assert _parse_meeting_type_durations("abc") is None


def test_booking_status_labels_are_russian() -> None:
    assert booking_status_label(BookingStatus.PENDING) == "ожидает подтверждения"
    assert booking_status_label(BookingStatus.CONFIRMED) == "подтверждена"
