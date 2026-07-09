import json

from ..endpoint import simple_endpoint


def _transform(rec: dict) -> dict:
    tags = rec.get("tags")
    return {
        "id": rec["id"],
        "day": rec["day"],
        "timestamp": rec.get("timestamp"),
        "text": rec.get("text"),
        "tags": json.dumps(tags) if tags else None,
    }


TAG_ENDPOINT = simple_endpoint("tag", pk="id", transform=_transform)
