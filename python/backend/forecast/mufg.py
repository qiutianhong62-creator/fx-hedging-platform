import re
from datetime import date, datetime
from html.parser import HTMLParser
from math import isfinite

import httpx

from backend.forecast.errors import ForecastFetchError, ForecastSourceInvalidError
from backend.forecast.quarters import parse_quarter_end
from backend.forecast.types import ForecastPoint, InstitutionForecastSnapshot


MUFG_FORECAST_URL = "https://mufgresearch.com/forecasts/"
REQUEST_TIMEOUT_SECONDS = 10.0
USER_AGENT = "fx-hedging-platform/0.1 market-data-client"
UPDATED_PATTERN = re.compile(
    r"Latest\s+FX\s+forecast\s+update:\s*"
    r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
)
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


class _MufgForecastParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page_text_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.in_heading = False
        self.last_heading = ""
        self.in_table = False
        self.table_heading = ""
        self.in_thead = False
        self.in_tbody = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.current_row: list[str] = []
        self.current_headers: tuple[str, ...] = ()
        self.current_body_rows: list[tuple[str, ...]] = []
        self.tables: list[
            tuple[str, tuple[str, ...], tuple[tuple[str, ...], ...]]
        ] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.in_heading = True
            self.heading_parts = []
        elif tag == "table":
            self.in_table = True
            self.table_heading = self.last_heading
            self.current_headers = ()
            self.current_body_rows = []
        elif self.in_table and tag == "thead":
            self.in_thead = True
        elif self.in_table and tag == "tbody":
            self.in_tbody = True
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag in {"th", "td"}:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        self.page_text_parts.append(data)
        if self.in_heading:
            self.heading_parts.append(data)
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.in_heading:
            self.last_heading = _normalize(" ".join(self.heading_parts))
            self.heading_parts = []
            self.in_heading = False
        elif self.in_table and tag in {"th", "td"} and self.in_cell:
            self.current_row.append(_normalize(" ".join(self.cell_parts)))
            self.cell_parts = []
            self.in_cell = False
        elif self.in_table and tag == "tr":
            row = tuple(self.current_row)
            if self.in_thead and row:
                self.current_headers = row
            elif self.in_tbody and row:
                self.current_body_rows.append(row)
            self.current_row = []
        elif self.in_table and tag == "thead":
            self.in_thead = False
        elif self.in_table and tag == "tbody":
            self.in_tbody = False
        elif self.in_table and tag == "table":
            self.tables.append(
                (
                    self.table_heading,
                    self.current_headers,
                    tuple(self.current_body_rows),
                )
            )
            self.in_table = False

    def usd_cny_candidates(
        self,
    ) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
        candidates: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        for heading, headers, rows in self.tables:
            if heading.casefold() != "fx rates":
                continue
            if not headers and rows:
                body_headers = rows[0]
                if not body_headers or body_headers[0] != "":
                    continue
                try:
                    tuple(parse_quarter_end(item) for item in body_headers[1:])
                except ForecastSourceInvalidError:
                    continue
                headers = ("Currency Pair", *body_headers[1:])
                rows = rows[1:]
            if not headers or headers[0].casefold() != "currency pair":
                continue
            for row in rows:
                if row and row[0].upper() == "USD/CNY":
                    candidates.append((headers, row))
        return candidates


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _positive_finite(raw_value: str) -> float:
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ForecastSourceInvalidError() from exc
    if not isfinite(value) or value <= 0:
        raise ForecastSourceInvalidError()
    return value


def _parse_updated_date(text: str, retrieved_on: date) -> date:
    matches = list(UPDATED_PATTERN.finditer(text))
    if not matches:
        raise ForecastSourceInvalidError()
    dates: set[date] = set()
    for match in matches:
        month = MONTHS.get(match.group(2).lower())
        if month is None:
            raise ForecastSourceInvalidError()
        try:
            updated_on = date(
                int(match.group(3)),
                month,
                int(match.group(1)),
            )
        except ValueError as exc:
            raise ForecastSourceInvalidError() from exc
        if updated_on > retrieved_on:
            raise ForecastSourceInvalidError()
        dates.add(updated_on)
    if len(dates) != 1:
        raise ForecastSourceInvalidError()
    return dates.pop()


def parse_mufg_forecast_html(
    html_text: str,
    retrieved_at_utc: datetime,
) -> InstitutionForecastSnapshot:
    if retrieved_at_utc.tzinfo is None:
        raise ForecastSourceInvalidError()
    parser = _MufgForecastParser()
    parser.feed(html_text)
    parser.close()
    candidates = parser.usd_cny_candidates()
    if len(candidates) != 1:
        raise ForecastSourceInvalidError()

    headers, row = candidates[0]
    if len(headers) != len(row) or len(headers) < 3:
        raise ForecastSourceInvalidError()
    points = tuple(
        ForecastPoint(
            parse_quarter_end(label),
            _positive_finite(raw_value),
        )
        for label, raw_value in zip(headers[1:], row[1:])
    )
    point_dates = [item.date for item in points]
    if point_dates != sorted(set(point_dates)):
        raise ForecastSourceInvalidError()
    if sum(item.date > retrieved_at_utc.date() for item in points) < 2:
        raise ForecastSourceInvalidError()

    updated_on = _parse_updated_date(
        " ".join(parser.page_text_parts),
        retrieved_at_utc.date(),
    )
    return InstitutionForecastSnapshot(
        institution="MUFG",
        currency_pair="USD/CNY",
        source_url=MUFG_FORECAST_URL,
        source_updated_date=updated_on,
        fetched_at_utc=retrieved_at_utc,
        points=points,
    )


class MufgForecastProvider:
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
                MUFG_FORECAST_URL,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ForecastFetchError() from exc
        return parse_mufg_forecast_html(response.text, retrieved_at_utc)
