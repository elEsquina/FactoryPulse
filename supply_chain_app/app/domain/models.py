from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProductProfile:
    code: str
    group: str
    subgroup: str
    plants: list[str] = field(default_factory=list)
    storages: list[str] = field(default_factory=list)
    avg_delivery_unit: float | None = None
    avg_production_unit: float | None = None
    avg_sales_order_unit: float | None = None
    total_delivery_unit: float | None = None
    total_production_unit: float | None = None
    observation_count: int = 0


@dataclass
class RoutedAnswer:
    strategy: str
    route_reason: str
    benchmark_reference: str
    answer: str
    sources: list[dict]
    cypher: str | None = None
    debug_context: str | None = None
