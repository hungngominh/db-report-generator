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
    explain_mode: str = "plan"
    explain_top_n: int = 5
    explain_analyze_top_n: int = 0
    explain_statement_timeout_ms: int = 3000
    explain_lock_timeout_ms: int = 500
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
        explain_mode=str(data.get("ExplainMode", "plan")),
        explain_top_n=int(data.get("ExplainTopN", 5)),
        explain_analyze_top_n=int(data.get("ExplainAnalyzeTopN", 0)),
        explain_statement_timeout_ms=int(data.get("ExplainStatementTimeoutMs", 3000)),
        explain_lock_timeout_ms=int(data.get("ExplainLockTimeoutMs", 500)),
        raw=data,
    )
