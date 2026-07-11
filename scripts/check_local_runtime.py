from __future__ import annotations

import asyncio

from app.diagnostics import DiagnosticsService
from app.persistence.database import AsyncSessionFactory
from app.persistence.repositories import SqlAlchemyTelegramRuntimeStore
from app.settings.config import get_settings
from app.worker.main import recover_jobs_once_async, run_worker_once_async


async def main() -> None:
    settings = get_settings()
    report = await DiagnosticsService(
        settings,
        session_factory=AsyncSessionFactory,
    ).build_report()
    for check in report.checks:
        if check.name in {"database", "worker"}:
            print(f"{check.name}_status {check.status}")

    store = SqlAlchemyTelegramRuntimeStore(session_factory=AsyncSessionFactory, settings=settings)
    schedule_settings = await store.get_schedule_settings()
    working_hours = await store.list_working_hours()
    meeting_types = await store.list_meeting_types_admin()
    restrictions = await store.list_upcoming_restrictions(from_date=settings_now_date())
    print(f"admin_schedule_timezone {schedule_settings.timezone}")
    print(f"admin_slot_step_minutes {schedule_settings.slot_step_minutes}")
    print(f"admin_working_hours_count {len(working_hours)}")
    print(f"admin_meeting_types_count {len(meeting_types)}")
    print(f"admin_restrictions_count {len(restrictions)}")

    recovered = await recover_jobs_once_async()
    result = await run_worker_once_async()
    print(f"worker_recovered {recovered}")
    print(f"worker_claimed {result.claimed}")
    if result.job_type:
        print(f"worker_job_type {result.job_type}")
    if result.status:
        print(f"worker_job_status {result.status}")


def settings_now_date():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(tz=ZoneInfo(get_settings().app_timezone)).date()


if __name__ == "__main__":
    asyncio.run(main())
