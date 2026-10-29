"""Packaged and development entry point for the SALOON DREEM API."""
from __future__ import annotations

import os

import uvicorn

from backend.app.main import app


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level=os.getenv("LOG_LEVEL", "info"), access_log=False)


if __name__ == "__main__":
    main()
