from app.logging.config import configure_logging, get_logger
from app.settings.config import get_settings

configure_logging()
logger = get_logger(__name__)


def run_worker_once() -> None:
    settings = get_settings()
    logger.info(
        "Worker tick completed",
        extra={
            "event": "worker_tick",
            "service": "worker",
            "poll_interval_seconds": settings.worker_poll_interval_seconds,
        },
    )


def main() -> None:
    settings = get_settings()
    logger.info(
        "Worker started",
        extra={
            "event": "worker_started",
            "service": "worker",
            "environment": settings.app_env,
        },
    )
    run_worker_once()
    logger.info("Worker stopped", extra={"event": "worker_stopped", "service": "worker"})


if __name__ == "__main__":
    main()
