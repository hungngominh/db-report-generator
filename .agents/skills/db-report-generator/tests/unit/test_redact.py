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


def test_redact_dsn_multi_host_no_leak():
    out = redact_dsn("postgresql://app:s3cr3t@host1.internal:5432,host2.internal:5432/prod")
    assert "s3cr3t" not in out
    assert "host1.internal" not in out
    assert "host2.internal" not in out


def test_redact_dsn_ipv6_host_no_leak():
    out = redact_dsn("postgresql://app:s3cr3t@[2001:db8::1]:5432/prod")
    assert "s3cr3t" not in out
    assert "2001:db8" not in out


def test_redact_dsn_query_string_secret_no_leak():
    out = redact_dsn("postgresql://app@db.example:5432/prod?password=s3cr3t&sslmode=require")
    assert "s3cr3t" not in out


def test_redact_dsn_no_password_not_fabricated():
    out = redact_dsn("postgresql://user@db.example:5432/mydb")
    assert out == "postgresql://user@«host»/mydb"
    assert "db.example" not in out


def test_redact_dsn_bare_fragment_secret_no_leak():
    out = redact_dsn("postgresql://app:s3cr3t@db.example/mydb#s3cr3t")
    assert "s3cr3t" not in out
    assert "db.example" not in out


def test_redact_dsn_password_with_slash_no_leak():
    out = redact_dsn("postgresql://app:pa/ss@db.internal.example:5432/mydb")
    assert "db.internal.example" not in out
    assert "pa/ss" not in out


def test_redact_dsn_password_with_hash_no_leak():
    out = redact_dsn("postgresql://app:pa#ss@db.internal.example:5432/mydb")
    assert "db.internal.example" not in out


def test_redact_dsn_slash_in_host_no_leak():
    out = redact_dsn("postgresql://ev/il.internal.example:5432/mydb")
    assert "il.internal.example" not in out


def test_redact_dsn_slash_in_host_with_userinfo_no_leak():
    out = redact_dsn("postgresql://app:s3cr3t@ev/il.internal.example:5432/mydb")
    assert "il.internal.example" not in out
    assert "s3cr3t" not in out
