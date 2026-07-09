from app.worker.jobs import WorkerRunResult
from app.worker.main import run_worker_once


class FakeWorkerService:
    async def run_once(self) -> WorkerRunResult:
        return WorkerRunResult(claimed=False)


def test_worker_tick_runs_without_error() -> None:
    result = run_worker_once(FakeWorkerService())

    assert result.claimed is False
