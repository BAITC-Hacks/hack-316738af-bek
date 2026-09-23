"""Production entry point for Docker and platforms that supply PORT."""

import os

import uvicorn


def main():
    port = int(os.getenv("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be in 1..65535")
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, workers=1)


if __name__ == "__main__":
    main()
