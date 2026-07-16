import re
from pathlib import Path

from scripts.lib.envparse import parse_env

SAMPLE = Path(__file__).resolve().parents[2] / "references" / "sample.env"


def test_sample_env_has_no_real_ip_or_secret():
    text = SAMPLE.read_text(encoding="utf-8")
    # no bare IPv4 literal
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text), "sample.env must not contain a real IP"
    assert "your_password_here" in text or "changeme" in text


def test_sample_env_still_parses():
    cfg = parse_env(SAMPLE)
    assert cfg.host and cfg.database and cfg.user
