from ..endpoint import simple_endpoint


def _transform(rec: dict) -> dict:
    return {
        "id": rec["id"],
        "tag_type_code": rec.get("tag_type_code"),
        "start_time": rec.get("start_time"),
        "end_time": rec.get("end_time"),
        "start_day": rec["start_day"],
        "end_day": rec.get("end_day"),
        "comment": rec.get("comment"),
        "custom_name": rec.get("custom_name"),
    }


ENHANCED_TAG_ENDPOINT = simple_endpoint("enhanced_tag", pk="id", transform=_transform)
