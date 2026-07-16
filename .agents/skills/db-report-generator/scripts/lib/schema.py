"""Validate report_data.json against the frozen v4 JSON Schema."""
import functools
import json
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "references" / "report-data.schema.json"


@functools.lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(load_schema())


def validate_report(data: dict) -> None:
    """Raise jsonschema.exceptions.ValidationError on the first violation."""
    _validator().validate(data)


def validation_errors(data: dict) -> list[str]:
    """Return all validation messages (empty list == valid)."""
    return [e.message for e in sorted(_validator().iter_errors(data), key=str)]
