from dataclasses import dataclass


@dataclass
class Product:
    id: int | None = None
    name: str = ""
    price: float = 0.0


TABLES: list[type] = [Product]
