from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class ForecastPoint:
    date: date
    spot: float


@dataclass(frozen=True)
class InstitutionForecastSnapshot:
    institution: str
    currency_pair: str
    source_url: str
    source_updated_date: date
    fetched_at_utc: datetime
    points: tuple[ForecastPoint, ...]


@dataclass(frozen=True)
class ForecastAnchor:
    source: str
    date: date
    spot: float


@dataclass(frozen=True)
class ForecastMatch:
    expected_spot: float
    method: str
    is_system_estimate: bool
    day_weight: float | None
    anchors: tuple[ForecastAnchor, ...]


class ForecastProvider(Protocol):
    def fetch(
        self,
        retrieved_at_utc: datetime,
    ) -> InstitutionForecastSnapshot: ...
