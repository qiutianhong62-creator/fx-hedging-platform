from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class FxObservation:
    date: date
    rate: float


@dataclass(frozen=True)
class CachedHistory:
    provider: str
    series_id: str
    query_start: date
    query_end: date
    fetched_at_utc: datetime
    observations: tuple[FxObservation, ...]


class HistoryProvider(Protocol):
    def fetch(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[FxObservation, ...]: ...
