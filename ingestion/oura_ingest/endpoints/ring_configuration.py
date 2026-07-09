from ..endpoint import Endpoint


def _transform(rec: dict) -> dict:
    return {
        "id": rec["id"],
        "color": rec.get("color"),
        "design": rec.get("design"),
        "firmware_version": rec.get("firmware_version"),
        "hardware_type": rec.get("hardware_type"),
        "set_up_at": rec.get("set_up_at"),
        "size": rec.get("size"),
    }


RING_CONFIGURATION_ENDPOINT = Endpoint(
    name="ring_configuration",
    api_path="ring_configuration",
    table="ring_configuration",
    pk="id",
    transform=_transform,
    query_mode="none",
)
