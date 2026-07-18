import json
import os
import tempfile
from datetime import date, datetime
from math import isfinite
from pathlib import Path

from backend.market.types import CachedHistory, FxObservation


def default_market_cache_path() -> Path:
    python_root = Path(__file__).resolve().parents[2]
    return python_root / ".cache" / "market-data" / "fred-dexchus-1y.json"


class JsonHistoryCache:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> CachedHistory | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            history = CachedHistory(
                provider=payload["provider"],
                series_id=payload["series_id"],
                query_start=date.fromisoformat(payload["query_start"]),
                query_end=date.fromisoformat(payload["query_end"]),
                fetched_at_utc=datetime.fromisoformat(
                    payload["fetched_at_utc"].replace("Z", "+00:00")
                ),
                observations=tuple(
                    FxObservation(date.fromisoformat(item["date"]), item["rate"])
                    for item in payload["observations"]
                ),
            )
            observation_dates = [item.date for item in history.observations]
            if (
                history.provider != "FRED"
                or history.series_id != "DEXCHUS"
                or history.fetched_at_utc.tzinfo is None
                or history.query_start > history.query_end
                or not history.observations
                or observation_dates != sorted(set(observation_dates))
                or any(
                    not isfinite(item.rate) or item.rate <= 0
                    for item in history.observations
                )
            ):
                return None
            return history
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def save(self, history: CachedHistory) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider": history.provider,
            "series_id": history.series_id,
            "query_start": history.query_start.isoformat(),
            "query_end": history.query_end.isoformat(),
            "fetched_at_utc": history.fetched_at_utc.isoformat().replace(
                "+00:00", "Z"
            ),
            "observations": [
                {"date": item.date.isoformat(), "rate": item.rate}
                for item in history.observations
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
