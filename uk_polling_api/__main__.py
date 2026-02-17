"""Run the UK Polling API server.

Usage:
    python -m uk_polling_api
    python -m uk_polling_api --host 0.0.0.0 --port 8080
"""

import argparse
import logging

import uvicorn


def main():
    parser = argparse.ArgumentParser(
        description="UK Polling Voting Intentions API"
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Bind port (default: 8000)"
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    uvicorn.run(
        "uk_polling_api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
