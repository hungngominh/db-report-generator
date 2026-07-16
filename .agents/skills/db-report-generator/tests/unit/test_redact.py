from scripts.lib.redact import contains_secret, redact_dsn, redact_value


def test_redact_dsn_hides_password():
    out = redact_dsn("postgresql://app:s3cr3t@10.0.0.5:5432/prod")
    assert "s3cr3t" not in out
    assert "app" in out and "prod" in out


def test_redact_dsn_hides_host_when_redacted():
    out = redact_dsn("postgresql://app:s3cr3t@db.internal.example:5432/prod")
    assert "db.internal.example" not in out


def test_redact_value_modes():
    assert redact_value("abc", "none") == "abc"
    assert redact_value("abc", "redact") == "«redacted»"
    hashed = redact_value("abc", "hash")
    assert hashed != "abc" and hashed.startswith("sha256:")


def test_contains_secret():
    assert contains_secret("dsn=...s3cr3t...", ["s3cr3t"])
    assert not contains_secret("clean text", ["s3cr3t"])
