from dataclasses import dataclass
from typing import Callable, Literal


@dataclass(frozen=True)
class Endpoint:
    name: str
    api_path: str
    table: str
    pk: str
    transform: Callable[[dict], dict]
    query_mode: Literal["date", "datetime", "none"] = "date"
    response_mode: Literal["collection", "single"] = "collection"
    initial_history_days: int | None = None
    always_full_sync: bool = False


def simple_endpoint(name: str, pk: str, transform: Callable[[dict], dict]) -> Endpoint:
    """Factory for endpoints where name == api_path == table."""
    return Endpoint(name=name, api_path=name, table=name, pk=pk, transform=transform)
