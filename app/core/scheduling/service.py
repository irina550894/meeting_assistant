from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.booking import MeetingType
from app.core.scheduling.entities import (
    AvailableSlot,
    BusyInterval,
    BusySource,
    RestrictionType,
    ScheduleRestriction,
    ScheduleSettings,
    SlotCalculationResult,
    SlotExclusionReason,
    WorkingHoursRule,
)
from app.core.scheduling.errors import SchedulingRuleError
from app.logging.config import get_logger

logger = get_logger(__name__)


class SlotCalculationService:
    def calculate_slots(
        self,
        *,
        target_date: date,
        meeting_type: MeetingType,
        duration_minutes: int | None,
        now: datetime,
        settings: ScheduleSettings,
        working_hours: list[WorkingHoursRule],
        restrictions: list[ScheduleRestriction],
        busy_intervals: list[BusyInterval],
    ) -> SlotCalculationResult:
        logger.info(
            "Slot calculation requested",
            extra={
                "event": "slot_calculation_requested",
                "date": target_date.isoformat(),
                "meeting_type": meeting_type.name,
            },
        )
        duration = self.resolve_duration(meeting_type, duration_minutes)
        timezone = ZoneInfo(settings.timezone)
        now_local = self._as_timezone(now, timezone)
        exclusions: Counter[SlotExclusionReason] = Counter()

        range_reason = self._booking_range_exclusion(target_date, now_local, settings)
        if range_reason:
            exclusions[range_reason] += 1
            return self._result([], exclusions, target_date, meeting_type.name)

        working_rule = self._working_rule_for_date(target_date, working_hours)
        if not working_rule or not working_rule.is_working_day:
            exclusions[SlotExclusionReason.NON_WORKING_DAY] += 1
            return self._result([], exclusions, target_date, meeting_type.name)

        if working_rule.start_time is None or working_rule.end_time is None:
            exclusions[SlotExclusionReason.INVALID_SETTINGS] += 1
            return self._result([], exclusions, target_date, meeting_type.name)

        if self._has_closed_day(target_date, restrictions):
            exclusions[SlotExclusionReason.CLOSED_DAY] += 1
            return self._result([], exclusions, target_date, meeting_type.name)

        slots: list[AvailableSlot] = []
        work_start = datetime.combine(target_date, working_rule.start_time, tzinfo=timezone)
        work_end = datetime.combine(target_date, working_rule.end_time, tzinfo=timezone)
        step = timedelta(minutes=settings.slot_step_minutes)
        duration_delta = timedelta(minutes=duration)

        candidate_start = work_start
        while candidate_start + duration_delta <= work_end:
            candidate_end = candidate_start + duration_delta
            reason = self._slot_exclusion(
                candidate_start=candidate_start,
                candidate_end=candidate_end,
                restrictions=restrictions,
                busy_intervals=busy_intervals,
                buffer_delta=timedelta(minutes=settings.meeting_buffer_minutes),
            )
            if reason:
                exclusions[reason] += 1
            else:
                slots.append(AvailableSlot(starts_at=candidate_start, ends_at=candidate_end))
            candidate_start += step

        return self._result(slots, exclusions, target_date, meeting_type.name)

    def resolve_duration(self, meeting_type: MeetingType, duration_minutes: int | None) -> int:
        if meeting_type.is_fixed_duration:
            fixed_duration = meeting_type.allowed_durations_minutes[0]
            if duration_minutes not in (None, fixed_duration):
                self._raise_rule(
                    "invalid_duration",
                    "Fixed meeting type duration cannot be changed.",
                )
            return fixed_duration

        if duration_minutes not in meeting_type.allowed_durations_minutes:
            self._raise_rule("invalid_duration", "Duration is not allowed for meeting type.")
        return duration_minutes

    def _booking_range_exclusion(
        self,
        target_date: date,
        now_local: datetime,
        settings: ScheduleSettings,
    ) -> SlotExclusionReason | None:
        first_available_date = now_local.date() + timedelta(days=settings.min_booking_lead_days)
        last_available_date = now_local.date() + timedelta(days=settings.booking_horizon_days)
        if target_date < first_available_date or target_date > last_available_date:
            return SlotExclusionReason.OUT_OF_BOOKING_RANGE
        return None

    def _working_rule_for_date(
        self,
        target_date: date,
        working_hours: list[WorkingHoursRule],
    ) -> WorkingHoursRule | None:
        weekday = target_date.weekday()
        return next((rule for rule in working_hours if rule.weekday == weekday), None)

    def _has_closed_day(
        self,
        target_date: date,
        restrictions: list[ScheduleRestriction],
    ) -> bool:
        return any(
            restriction.restriction_date == target_date
            and restriction.restriction_type == RestrictionType.CLOSED_DAY
            for restriction in restrictions
        )

    def _slot_exclusion(
        self,
        *,
        candidate_start: datetime,
        candidate_end: datetime,
        restrictions: list[ScheduleRestriction],
        busy_intervals: list[BusyInterval],
        buffer_delta: timedelta,
    ) -> SlotExclusionReason | None:
        if self._overlaps_manual_restriction(candidate_start, candidate_end, restrictions):
            return SlotExclusionReason.MANUAL_RESTRICTION

        for interval in busy_intervals:
            reason = self._busy_interval_exclusion(
                candidate_start,
                candidate_end,
                interval,
                buffer_delta,
            )
            if reason:
                return reason
        return None

    def _overlaps_manual_restriction(
        self,
        candidate_start: datetime,
        candidate_end: datetime,
        restrictions: list[ScheduleRestriction],
    ) -> bool:
        for restriction in restrictions:
            if restriction.restriction_type != RestrictionType.TIME_INTERVAL:
                continue
            if restriction.restriction_date != candidate_start.date():
                continue
            if restriction.start_time is None or restriction.end_time is None:
                continue

            interval_start = datetime.combine(
                restriction.restriction_date,
                restriction.start_time,
                tzinfo=candidate_start.tzinfo,
            )
            interval_end = datetime.combine(
                restriction.restriction_date,
                restriction.end_time,
                tzinfo=candidate_start.tzinfo,
            )
            if self._overlaps(candidate_start, candidate_end, interval_start, interval_end):
                return True
        return False

    def _busy_interval_exclusion(
        self,
        candidate_start: datetime,
        candidate_end: datetime,
        interval: BusyInterval,
        buffer_delta: timedelta,
    ) -> SlotExclusionReason | None:
        if (
            interval.all_day
            and interval.starts_at.date() <= candidate_start.date() <= interval.ends_at.date()
        ):
            return self._reason_for_busy_source(interval.source)

        busy_start = self._as_timezone(interval.starts_at, candidate_start.tzinfo) - buffer_delta
        busy_end = self._as_timezone(interval.ends_at, candidate_start.tzinfo) + buffer_delta
        if self._overlaps(candidate_start, candidate_end, busy_start, busy_end):
            return self._reason_for_busy_source(interval.source)
        return None

    def _reason_for_busy_source(self, source: BusySource) -> SlotExclusionReason:
        if source == BusySource.CALENDAR:
            return SlotExclusionReason.CALENDAR_BUSY
        if source == BusySource.RESERVATION:
            return SlotExclusionReason.ACTIVE_RESERVATION
        return SlotExclusionReason.CONFIRMED_BOOKING

    def _overlaps(
        self,
        first_start: datetime,
        first_end: datetime,
        second_start: datetime,
        second_end: datetime,
    ) -> bool:
        return first_start < second_end and second_start < first_end

    def _as_timezone(self, value: datetime, timezone) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone)
        return value.astimezone(timezone)

    def _result(
        self,
        slots: list[AvailableSlot],
        exclusions: Counter[SlotExclusionReason],
        target_date: date,
        meeting_type_name: str,
    ) -> SlotCalculationResult:
        result = SlotCalculationResult(slots=slots, exclusion_counts=dict(exclusions))
        logger.info(
            "Slots calculated",
            extra={
                "event": "slots_calculated",
                "date": target_date.isoformat(),
                "meeting_type": meeting_type_name,
                "slots_count": len(slots),
                "exclusion_counts": {reason.value: count for reason, count in exclusions.items()},
            },
        )
        return result

    def _raise_rule(self, rule: str, message: str) -> None:
        logger.warning(
            "Scheduling rule failed",
            extra={"event": "scheduling_rule_failed", "rule": rule},
        )
        raise SchedulingRuleError(rule, message)
