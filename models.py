from datetime import date, datetime
from typing import Any

from bson import ObjectId


def _serialize_value(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    return value


def serialize_document(document: dict[str, Any]) -> dict[str, Any]:
    """Convert MongoDB values into types that can be returned as JSON."""
    return _serialize_value(document)
