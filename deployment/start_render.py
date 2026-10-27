"""Start the Render web service after applying database migrations."""

import os
import subprocess
import sys


def main() -> None:
    subprocess.run(["alembic", "upgrade", "head"], check=True)

    port = os.environ.get("PORT", "10000")
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
        ],
    )


if __name__ == "__main__":
    main()
