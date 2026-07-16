"""Throwaway Docker Postgres for live-DB tests. Skips cleanly without Docker."""
import shutil
import socket
import subprocess
import time

import psycopg2


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=True)
        return True
    except Exception:
        return False


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class PostgresContainer:
    def __init__(self, image: str = "postgres:16"):
        self.image = image
        self.name = None
        self.port = None

    @property
    def dsn_kwargs(self) -> dict:
        return {
            "host": "127.0.0.1", "port": self.port, "dbname": "postgres",
            "user": "postgres", "password": "postgres", "connect_timeout": 10,
        }

    @property
    def dsn_url(self) -> str:
        return f"postgresql://postgres:postgres@127.0.0.1:{self.port}/postgres"

    def __enter__(self):
        self.port = _free_port()
        self.name = f"dbrep-test-{self.port}"
        try:
            subprocess.run(
                ["docker", "run", "-d", "--rm", "--name", self.name,
                 "-e", "POSTGRES_PASSWORD=postgres",
                 "-p", f"{self.port}:5432", self.image],
                check=True, capture_output=True,
            )
            self._wait_ready()
        except Exception:
            subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
            raise
        return self

    def _wait_ready(self, timeout: float = 60.0):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                conn = psycopg2.connect(**self.dsn_kwargs)
                conn.close()
                return
            except Exception as e:  # noqa: BLE001 - retry until ready
                last = e
                time.sleep(0.5)
        raise RuntimeError(f"postgres container not ready in {timeout}s: {last}")

    def __exit__(self, *exc):
        if self.name:
            subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
