import re
from datetime import date, datetime
from html.parser import HTMLParser
from math import isfinite

import httpx

from backend.forecast.errors import ForecastFetchError, ForecastSourceInvalidError
from backend.forecast.types import ForecastPoint, InstitutionForecastSnapshot


ING_FORECAST_URL = "https://think.ing.com/forecasts/"
REQUEST_TIMEOUT_SECONDS = 10.0
USER_AGENT = "fx-hedging-platform/0.1 market-data-client"
QUARTER_PATTERN = re.compile(r"([1-4])Q(\d{2})F")
UPDATED_PATTERN = re.compile(r"Last updated:\s*(\d{1,2})\s+([A-Za-z]+)")
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


class _IngFxParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_fx = False
        self.fx_div_depth = 0
        self.in_thead = False
        self.in_tbody = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.current_row: list[str] = []
        self.current_headers: tuple[str, ...] = ()
        self.fx_text_parts: list[str] = []
        self.candidates: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "div":
            if self.in_fx:
                self.fx_div_depth += 1
            elif attributes.get("id") == "fx":
                self.in_fx = True
                self.fx_div_depth = 1
        if not self.in_fx:
            return
        if tag == "thead":
            self.in_thead = True
        elif tag == "tbody":
            self.in_tbody = True
        elif tag == "tr":
            self.current_row = []
        elif tag in {"th", "td"}:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_fx:
            self.fx_text_parts.append(data)
        if self.in_fx and self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.in_fx:
            return
        if tag in {"th", "td"} and self.in_cell:
            self.current_row.append(" ".join(self.cell_parts).strip())
            self.in_cell = False
            self.cell_parts = []
        elif tag == "tr":
            row = tuple(self.current_row)
            if self.in_thead and row:
                self.current_headers = row
            elif self.in_tbody and len(row) >= 2:
                if row[0] == "China" and row[1] == "USD/CNY":
                    self.candidates.append((self.current_headers, row))
            self.current_row = []
        elif tag == "thead":
            self.in_thead = False
        elif tag == "tbody":
            self.in_tbody = False
        if tag == "div":
            self.fx_div_depth -= 1
            if self.fx_div_depth == 0:
                self.in_fx = False


def parse_quarter_label(label: str) -> date:
    match = QUARTER_PATTERN.fullmatch(label.strip())
    if match is None:
        raise ForecastSourceInvalidError()
    quarter = int(match.group(1))
    year = 2000 + int(match.group(2))
    month_day = {
        1: (3, 31),
        2: (6, 30),
        3: (9, 30),
        4: (12, 31),
    }
    month, day = month_day[quarter]
    return date(year, month, day)


def _resolve_updated_date(text: str, retrieved_on: date) -> date:
    match = UPDATED_PATTERN.search(text)
    if match is None:
        raise ForecastSourceInvalidError()
    day = int(match.group(1))
    month = MONTHS.get(match.group(2).lower())
    if month is None:
        raise ForecastSourceInvalidError()
    candidates: list[date] = []
    for year in (retrieved_on.year, retrieved_on.year - 1):
        try:
            candidate = date(year, month, day)
        except ValueError as exc:
            raise ForecastSourceInvalidError() from exc
        if candidate <= retrieved_on:
            candidates.append(candidate)
    if not candidates:
        raise ForecastSourceInvalidError()
    return max(candidates)


def parse_ing_forecast_html(
    html_text: str,
    retrieved_at_utc: datetime,
) -> InstitutionForecastSnapshot:
    if retrieved_at_utc.tzinfo is None:
        raise ForecastSourceInvalidError()
    parser = _IngFxParser()
    parser.feed(html_text)
    parser.close()
    if len(parser.candidates) != 1:
        raise ForecastSourceInvalidError()

    headers, row = parser.candidates[0]
    if len(headers) != len(row) or len(headers) < 4:
        raise ForecastSourceInvalidError()
    points: list[ForecastPoint] = []
    for label, raw_spot in zip(headers[2:], row[2:]):
        point_date = parse_quarter_label(label)
        try:
            spot = float(raw_spot)
        except ValueError as exc:
            raise ForecastSourceInvalidError() from exc
        if not isfinite(spot) or spot <= 0:
            raise ForecastSourceInvalidError()
        points.append(ForecastPoint(point_date, spot))

    point_dates = [item.date for item in points]
    if point_dates != sorted(set(point_dates)):
        raise ForecastSourceInvalidError()
    future_count = sum(
        item.date > retrieved_at_utc.date()
        for item in points
    )
    if future_count < 2:
        raise ForecastSourceInvalidError()
    updated_date = _resolve_updated_date(
        " ".join(parser.fx_text_parts),
        retrieved_at_utc.date(),
    )
    return InstitutionForecastSnapshot(
        institution="ING",
        currency_pair="USD/CNY",
        source_url=ING_FORECAST_URL,
        source_updated_date=updated_date,
        fetched_at_utc=retrieved_at_utc,
        points=tuple(points),
    )


class IngForecastProvider:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client or httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    def fetch(
        self,
        retrieved_at_utc: datetime,
    ) -> InstitutionForecastSnapshot:
        try:
            response = self._http_client.get(
                ING_FORECAST_URL,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ForecastFetchError() from exc
        return parse_ing_forecast_html(response.text, retrieved_at_utc)
