from ..endpoint import Endpoint


def _transform(rec: dict) -> dict:
    return {
        "id": rec["id"],
        "age": rec.get("age"),
        "weight": rec.get("weight"),
        "height": rec.get("height"),
        "biological_sex": rec.get("biological_sex"),
    }


PERSONAL_INFO_ENDPOINT = Endpoint(
    name="personal_info",
    api_path="personal_info",
    table="personal_info",
    pk="id",
    transform=_transform,
    query_mode="none",
    response_mode="single",
)
