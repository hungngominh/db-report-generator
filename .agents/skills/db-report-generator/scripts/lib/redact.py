"""Redaction helpers — never let secrets reach logs/output."""
import hashlib
import re

_DSN_RE = re.compile(
    r"^(?P<scheme>[a-zA-Z][\w+.\-]*)://(?P<authority>[^/?#]*)(?P<tail>[/?#].*)?$",
    re.DOTALL,
)


def redact_dsn(dsn: str) -> str:
    """Hide password, ALL host(s) and any query-string secrets in a DSN.

    Redacts the whole authority host block (covers multi-host libpq strings
    and bracketed IPv6) rather than echoing it; over-redacts the query string
    rather than risk leaking a credential carried there. Fails safe: an
    unparseable DSN becomes a fixed placeholder, never the raw input.
    """
    m = _DSN_RE.match(dsn.strip())
    if not m:
        return "«redacted-dsn»"
    scheme = m.group("scheme")
    authority = m.group("authority")
    tail = m.group("tail") or ""

    if "@" in authority:
        userinfo, _hostinfo = authority.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        cred = f"{user}:«redacted»" if ":" in userinfo else user
        redacted_authority = f"{cred}@«host»"
    else:
        redacted_authority = "«host»"

    if "?" in tail:
        redacted_tail = tail.split("?", 1)[0] + "?«redacted»"
    else:
        redacted_tail = tail

    return f"{scheme}://{redacted_authority}{redacted_tail}"


def redact_value(text: str, mode: str) -> str:
    if mode == "none":
        return text
    if mode == "hash":
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return "«redacted»"


def contains_secret(text: str, secrets: list[str]) -> bool:
    return any(s and s in text for s in secrets)
