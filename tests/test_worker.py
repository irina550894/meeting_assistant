from app.worker.main import run_worker_once


def test_worker_tick_runs_without_error() -> None:
    run_worker_once()
