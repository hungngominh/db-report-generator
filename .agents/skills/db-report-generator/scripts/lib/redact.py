"""Redaction helpers — never let secrets reach logs/output."""
import hashlib
import re

_DSN_RE = re.compile(r"^(?P<scheme>\w+)://(?P<user>[^:@/]+)(?::[^@/]+)?@(?P<host>[^:/]+)(?P<rest>[:/].*)?$")


def redact_dsn(dsn: str) -> str:
    m = _DSN_RE.match(dsn.strip())
    if not m:
        return "«redacted-dsn»"
    return f"{m.group('scheme')}://{m.group('user')}:«redacted»@«host»{m.group('rest') or ''}"


def redact_value(text: str, mode: str) -> str:
    if mode == "none":
        return text
    if mode == "hash":
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return "«redacted»"


def contains_secret(text: str, secrets: list[str]) -> bool:
    return any(s and s in text for s in secrets)
