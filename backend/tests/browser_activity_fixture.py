"""Disposable loopback API for the public activity browser check, never deployment.

``--fixture`` serves the generated fictional activity package; without it the view must be
disabled (no authorization file exists in the temporary folder). Reads no .env, uses a
temporary SQLite store and never touches real packages. Stdin EOF shuts it down.
"""

import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import sys
from tempfile import TemporaryDirectory

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402


def main():
    temporary_root = Path(__file__).resolve().parents[1] / ".tmp"
    temporary_root.mkdir(exist_ok=True)
    fixture = "--fixture" in sys.argv
    with TemporaryDirectory(prefix="activity-browser-", dir=temporary_root) as directory:
        settings = config.Settings(
            _env_file=None, secret_key=secrets.token_urlsafe(48), database_url=f"sqlite:///{Path(directory) / 'fixture.db'}",
            auto_create_schema=True, cors_origins=os.environ.get("SIGARD_BROWSER_FRONTEND_URL", "http://127.0.0.1:5173"),
            sigard_public_activity="fixture" if fixture else None,
            public_activity_dir=str(Path(directory) / "no-package"),
            public_activity_authorization=str(Path(directory) / "no-authorization.private.json"),
        )
        config.get_settings = lambda: settings
        from app.main import create_app

        app = create_app()
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        listener.setblocking(False)
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))

        async def run():
            async def stop_on_input():
                await asyncio.to_thread(sys.stdin.readline)
                server.should_exit = True
            print(json.dumps({"port": listener.getsockname()[1], "fixture": "sigard-activity", "enabled": fixture}), flush=True)
            await asyncio.gather(server.serve(sockets=[listener]), stop_on_input())
        try:
            asyncio.run(run())
        finally:
            listener.close()
            app.state.engine.dispose()


if __name__ == "__main__":
    main()
