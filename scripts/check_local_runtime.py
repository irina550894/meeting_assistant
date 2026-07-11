from __future__ import annotations

import asyncio

from app.diagnostics import DiagnosticsService
from app.persistence.database import AsyncSessionFactory
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

    recovered = await recover_jobs_once_async()
    result = await run_worker_once_async()
    print(f"worker_recovered {recovered}")
    print(f"worker_claimed {result.claimed}")
    if result.job_type:
        print(f"worker_job_type {result.job_type}")
    if result.status:
        print(f"worker_job_status {result.status}")


if __name__ == "__main__":
    asyncio.run(main())
