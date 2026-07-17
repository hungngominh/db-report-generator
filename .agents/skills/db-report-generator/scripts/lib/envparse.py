"""Parse the v3 JSON `.env` config into a typed DbConfig."""
import json
from dataclasses import dataclass, field
from pathlib import Path

_REQUIRED = ("ServerName", "CatalogName", "Username", "Password")


@dataclass
class DbConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    project_name: str = ""
    code_path: str = ""
    sampling_window_seconds: int = 30
    raw: dict = field(default_factory=dict)


def parse_env(source) -> DbConfig:
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8")
    else:
        text = source
    data = json.loads(text)
    missing = [k for k in _REQUIRED if k not in data or data[k] in (None, "")]
    if missing:
        raise ValueError(f".env missing required keys: {', '.join(missing)}")
    return DbConfig(
        host=str(data["ServerName"]),
        port=int(data.get("Port", 5432)),
        database=str(data["CatalogName"]),
        user=str(data["Username"]),
        password=str(data["Password"]),
        project_name=str(data.get("ProjectName", "")),
        code_path=str(data.get("CodePath", "")),
        sampling_window_seconds=int(data.get("SamplingWindowSeconds", 30)),
        raw=data,
    )
