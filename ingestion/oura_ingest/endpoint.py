from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Endpoint:
    name: str
    api_path: str
    table: str
    pk: str
    transform: Callable[[dict], dict]


def simple_endpoint(name: str, pk: str, transform: Callable[[dict], dict]) -> Endpoint:
    """Factory for endpoints where name == api_path == table."""
    return Endpoint(name=name, api_path=name, table=name, pk=pk, transform=transform)
