import json
import os
import tempfile
from datetime import date, datetime
from math import isfinite
from pathlib import Path

from backend.forecast.ing import ING_FORECAST_URL
from backend.forecast.types import ForecastPoint, InstitutionForecastSnapshot


def default_forecast_cache_path() -> Path:
    python_root = Path(__file__).resolve().parents[2]
    return python_root / ".cache" / "market-data" / "ing-usdcny-forecast.json"


class JsonForecastCache:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> InstitutionForecastSnapshot | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            snapshot = InstitutionForecastSnapshot(
                institution=payload["institution"],
                currency_pair=payload["currency_pair"],
                source_url=payload["source_url"],
                source_updated_date=date.fromisoformat(
                    payload["source_updated_date"]
                ),
                fetched_at_utc=datetime.fromisoformat(
                    payload["fetched_at_utc"].replace("Z", "+00:00")
                ),
                points=tuple(
                    ForecastPoint(
                        date.fromisoformat(item["date"]),
                        item["spot"],
                    )
                    for item in payload["points"]
                ),
            )
            point_dates = [item.date for item in snapshot.points]
            if (
                snapshot.institution != "ING"
                or snapshot.currency_pair != "USD/CNY"
                or snapshot.source_url != ING_FORECAST_URL
                or snapshot.fetched_at_utc.tzinfo is None
                or snapshot.source_updated_date > snapshot.fetched_at_utc.date()
                or len(snapshot.points) < 2
                or point_dates != sorted(set(point_dates))
                or any(
                    not isfinite(item.spot) or item.spot <= 0
                    for item in snapshot.points
                )
            ):
                return None
            return snapshot
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def save(self, snapshot: InstitutionForecastSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "institution": snapshot.institution,
            "currency_pair": snapshot.currency_pair,
            "source_url": snapshot.source_url,
            "source_updated_date": snapshot.source_updated_date.isoformat(),
            "fetched_at_utc": snapshot.fetched_at_utc.isoformat().replace(
                "+00:00", "Z"
            ),
            "points": [
                {"date": item.date.isoformat(), "spot": item.spot}
                for item in snapshot.points
            ],
        }
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                delete=False,
            ) as temp_file:
                temp_name = temp_file.name
                json.dump(payload, temp_file, ensure_ascii=False)
            os.replace(temp_name, self.path)
        finally:
            if temp_name is not None and Path(temp_name).exists():
                Path(temp_name).unlink()
