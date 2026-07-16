"""Redaction helpers — never let secrets reach logs/output."""
import hashlib
import re

_DSN_RE = re.compile(
    r"^(?P<scheme>[a-zA-Z][\w+.\-]*)://(?P<authority>[^/?#]*)(?P<tail>[/?#].*)?$",
    re.DOTALL,
)


def redact_dsn(dsn: str) -> str:
    """Hide password, ALL host(s), query AND fragment secrets in a DSN.

    Redacts the whole authority host block (multi-host libpq, bracketed IPv6),
    drops both query (?) and fragment (#). If an unescaped reserved char in the
    userinfo/host pushes an '@' into the tail, the authority parse is unsafe, so
    the whole locator is over-redacted. Fails safe: unparseable → placeholder,
    never the raw input.
    """
    m = _DSN_RE.match(dsn.strip())
    if not m:
        return "«redacted-dsn»"
    scheme = m.group("scheme")
    authority = m.group("authority")
    tail = m.group("tail") or ""

    # '@' in the tail means the authority capture under-consumed (unescaped
    # reserved char in userinfo/host) — cannot safely preserve the tail.
    if "@" in tail:
        return f"{scheme}://«redacted»"

    if "@" in authority:
        userinfo, _hostinfo = authority.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        cred = f"{user}:«redacted»" if ":" in userinfo else user
        redacted_authority = f"{cred}@«host»"
    else:
        redacted_authority = "«host»"

    # Drop BOTH query and fragment — either can carry secrets.
    path = re.split(r"[?#]", tail, maxsplit=1)[0]
    redacted_tail = path if path == tail else path + "?«redacted»"

    return f"{scheme}://{redacted_authority}{redacted_tail}"


def redact_value(text: str, mode: str) -> str:
    if mode == "none":
        return text
    if mode == "hash":
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return "«redacted»"


def contains_secret(text: str, secrets: list[str]) -> bool:
    return any(s and s in text for s in secrets)
