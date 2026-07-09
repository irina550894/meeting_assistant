import asyncio

from app.integrations.telegram.runtime import run_local_polling


def main() -> None:
    asyncio.run(run_local_polling())


if __name__ == "__main__":
    main()
