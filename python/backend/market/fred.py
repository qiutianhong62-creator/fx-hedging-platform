import csv
from datetime import date
from io import StringIO
from math import isfinite

import httpx

from backend.market.errors import MarketDataFetchError, MarketDataInvalidError
from backend.market.types import FxObservation


FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_SERIES_ID = "DEXCHUS"
REQUEST_TIMEOUT_SECONDS = 10.0


def parse_fred_csv(csv_text: str) -> tuple[FxObservation, ...]:
    reader = csv.DictReader(StringIO(csv_text))
    if reader.fieldnames is None or not {
        "observation_date",
        FRED_SERIES_ID,
    }.issubset(reader.fieldnames):
        raise MarketDataInvalidError()

    by_date: dict[date, FxObservation] = {}
    for row in reader:
        raw_rate = (row.get(FRED_SERIES_ID) or "").strip()
        if raw_rate in {"", "."}:
            continue
        try:
            observation_date = date.fromisoformat(
                (row.get("observation_date") or "").strip()
            )
            rate = float(raw_rate)
        except (TypeError, ValueError) as exc:
            raise MarketDataInvalidError() from exc
        if not isfinite(rate) or rate <= 0:
            raise MarketDataInvalidError()
        by_date[observation_date] = FxObservation(observation_date, rate)

    return tuple(by_date[key] for key in sorted(by_date))


class FredHistoryProvider:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client or httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    def fetch(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[FxObservation, ...]:
        try:
            response = self._http_client.get(
                FRED_CSV_URL,
                params={
                    "id": FRED_SERIES_ID,
                    "cosd": start_date.isoformat(),
                    "coed": end_date.isoformat(),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataFetchError() from exc
        return parse_fred_csv(response.text)
