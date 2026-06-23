import argparse
import logging
from power_agent.storage import init_db
from power_agent.collector import run_collector_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("power_agent")


def main():
    parser = argparse.ArgumentParser(description="Power Consumption AI Agent")
    parser.add_argument(
        "mode",
        choices=["collect", "api", "all"],
        help="Run mode: collect (data), api (server), all (both)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Data collection interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8765,
        help="API server port (default: 8765)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Auto-reload server on code changes",
    )

    args = parser.parse_args()
    init_db()

    if args.mode == "collect":
        logger.info("Starting data collector (interval=%ds)", args.interval)
        run_collector_loop(args.interval)

    elif args.mode == "api":
        import uvicorn
        logger.info("Starting API server on port %d", args.api_port)
        uvicorn.run("power_agent.api:app", host="0.0.0.0", port=args.api_port, reload=args.reload, log_level="info")

    elif args.mode == "all":
        import threading
        import uvicorn
        from power_agent.collector import collect_and_store
        collect_and_store()
        collator = threading.Thread(
            target=run_collector_loop, args=(args.interval,), daemon=True
        )
        collator.start()
        logger.info("Starting API server + collector on port %d", args.api_port)
        uvicorn.run("power_agent.api:app", host="0.0.0.0", port=args.api_port, reload=args.reload, log_level="info")


if __name__ == "__main__":
    main()
