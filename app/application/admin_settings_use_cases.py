from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from app.integrations.telegram.ports import (
    AdminMeetingType,
    AdminScheduleRestriction,
    AdminScheduleSettings,
    AdminSettingsStore,
    AdminWorkingHoursRule,
)


class AdminSettingsUseCaseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AdminSettingsUseCaseDeps:
    admin_settings: AdminSettingsStore


class AdminSettingsUseCases:
    def __init__(self, deps: AdminSettingsUseCaseDeps) -> None:
        self.deps = deps

    async def get_schedule_settings(self) -> AdminScheduleSettings:
        return await self.deps.admin_settings.get_schedule_settings()

    async def list_working_hours(self) -> list[AdminWorkingHoursRule]:
        return await self.deps.admin_settings.list_working_hours()

    async def list_restrictions(self, *, from_date: date) -> list[AdminScheduleRestriction]:
        return await self.deps.admin_settings.list_upcoming_restrictions(from_date=from_date)

    async def add_closed_day_restriction(
        self,
        *,
        restriction_date: date,
        admin_comment: str | None,
    ) -> None:
        await self.deps.admin_settings.add_closed_day_restriction(
            restriction_date=restriction_date,
            admin_comment=admin_comment,
        )

    async def add_time_interval_restriction(
        self,
        *,
        restriction_date: date,
        start_time: time,
        end_time: time,
        admin_comment: str | None,
    ) -> None:
        if start_time >= end_time:
            raise AdminSettingsUseCaseError(
                "invalid_time_interval",
                "Restriction start time must be before end time.",
            )
        await self.deps.admin_settings.add_time_interval_restriction(
            restriction_date=restriction_date,
            start_time=start_time,
            end_time=end_time,
            admin_comment=admin_comment,
        )

    async def delete_restriction(self, restriction_id: UUID) -> None:
        deleted = await self.deps.admin_settings.delete_restriction(restriction_id)
        if not deleted:
            raise AdminSettingsUseCaseError(
                "restriction_not_found",
                "Schedule restriction was not found.",
            )

    async def list_meeting_types_admin(self) -> list[AdminMeetingType]:
        return await self.deps.admin_settings.list_meeting_types_admin()

    async def add_meeting_type(
        self,
        *,
        name: str,
        allowed_durations_minutes: tuple[int, ...],
        is_fixed_duration: bool,
    ) -> AdminMeetingType:
        meeting_type = await self.deps.admin_settings.add_meeting_type(
            name=name,
            allowed_durations_minutes=allowed_durations_minutes,
            is_fixed_duration=is_fixed_duration,
        )
        if meeting_type is None:
            raise AdminSettingsUseCaseError(
                "meeting_type_already_exists",
                "Meeting type already exists.",
            )
        return meeting_type

    async def set_meeting_type_active(self, meeting_type_id: UUID, *, is_active: bool) -> None:
        updated = await self.deps.admin_settings.set_meeting_type_active(
            meeting_type_id,
            is_active=is_active,
        )
        if not updated:
            raise AdminSettingsUseCaseError(
                "meeting_type_not_found",
                "Meeting type was not found.",
            )
