"""Redaction helpers — never let secrets reach logs/output."""
import hashlib
import re

_DSN_RE = re.compile(
    r"^(?P<scheme>[a-zA-Z][\w+.\-]*)://(?P<authority>[^/?#]*)(?P<tail>[/?#].*)?$",
    re.DOTALL,
)


def redact_dsn(dsn: str) -> str:
    """Hide password, ALL host(s), query AND fragment secrets in a DSN.

    Over-redacts aggressively: the db-name path is preserved ONLY when it is a
    single clean token (``/[\\w.-]+``); anything unusual (host material leaking
    into the path via an unescaped '/', extra segments, ports, etc.) is
    replaced. Fails safe: unparseable input becomes a placeholder, never raw.
    """
    m = _DSN_RE.match(dsn.strip())
    if not m:
        return "«redacted-dsn»"
    scheme = m.group("scheme")
    authority = m.group("authority")
    tail = m.group("tail") or ""

    # '@' in the tail means the authority under-consumed → unsafe to preserve.
    if "@" in tail:
        return f"{scheme}://«redacted»"

    if "@" in authority:
        userinfo, _hostinfo = authority.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        cred = f"{user}:«redacted»" if ":" in userinfo else user
        redacted_authority = f"{cred}@«host»"
    else:
        redacted_authority = "«host»"

    # Preserve only a single clean db-name segment; over-redact anything else
    # (covers host material that leaked into the path via an unescaped '/').
    path = re.split(r"[?#]", tail, maxsplit=1)[0]
    if path in ("", "/"):
        redacted_tail = path
    elif re.fullmatch(r"/[\w.\-]+", path):
        redacted_tail = path if path == tail else path + "?«redacted»"
    else:
        redacted_tail = "/«redacted»"

    return f"{scheme}://{redacted_authority}{redacted_tail}"


def redact_value(text: str, mode: str) -> str:
    if mode == "none":
        return text
    if mode == "hash":
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return "«redacted»"


def contains_secret(text: str, secrets: list[str]) -> bool:
    return any(s and s in text for s in secrets)
