from datetime import date, datetime, timezone

import httpx
import pytest

from backend.forecast.errors import ForecastFetchError, ForecastSourceInvalidError
from backend.forecast.mufg import (
    MUFG_FORECAST_URL,
    MufgForecastProvider,
    parse_mufg_forecast_html,
)


RETRIEVED_AT = datetime(2026, 8, 4, 10, tzinfo=timezone.utc)


def mufg_html(
    *,
    updated: str = "03 July 2026",
    pair: str = "USD/CNY",
) -> str:
    return f"""
    <html><body>
      <p>Latest FX forecast update: {updated}</p>
      <h2>Economic forecasts</h2>
      <table>
        <thead><tr><th>Economy</th><th>Q3 2026</th></tr></thead>
        <tbody><tr><td>China</td><td>99</td></tr></tbody>
      </table>
      <h2>FX Rates</h2>
      <table>
        <thead>
          <tr><th>Currency Pair</th><th>Q3 2026</th><th>Q4 2026</th><th>Q1 2027</th><th>Q2 2027</th></tr>
        </thead>
        <tbody>
          <tr><td>{pair}</td><td>6.7000</td><td>6.6500</td><td>6.6000</td><td>6.6000</td></tr>
        </tbody>
      </table>
    </body></html>
    """


def test_parser_reads_only_fx_usd_cny_and_full_update_date() -> None:
    result = parse_mufg_forecast_html(mufg_html(), RETRIEVED_AT)

    assert result.institution == "MUFG"
    assert result.currency_pair == "USD/CNY"
    assert result.source_url == MUFG_FORECAST_URL
    assert result.source_updated_date == date(2026, 7, 3)
    assert result.fetched_at_utc == RETRIEVED_AT
    assert [(item.date, item.spot) for item in result.points] == [
        (date(2026, 9, 30), 6.70),
        (date(2026, 12, 31), 6.65),
        (date(2027, 3, 31), 6.60),
        (date(2027, 6, 30), 6.60),
    ]


def test_parser_supports_mufg_header_in_first_body_row() -> None:
    actual_structure = """
    <p>Latest FX forecast update: 03 August 2026</p>
    <h3>FX Rates</h3>
    <table><tbody>
      <tr><td></td><td>Q3 2026</td><td>Q4 2026</td><td>Q1 2027</td><td>Q2 2027</td></tr>
      <tr><td>USD/CNY</td><td>6.7000</td><td>6.6500</td><td>6.6000</td><td>6.6000</td></tr>
    </tbody></table>
    """

    result = parse_mufg_forecast_html(actual_structure, RETRIEVED_AT)

    assert result.source_updated_date == date(2026, 8, 3)
    assert [item.spot for item in result.points] == [6.7, 6.65, 6.6, 6.6]


@pytest.mark.parametrize(
    "html_text",
    [
        mufg_html().replace("FX Rates", "Interest Rates"),
        mufg_html(pair="EUR/USD"),
        mufg_html().replace(
            "</tbody>",
            "<tr><td>USD/CNY</td><td>6.7</td><td>6.6</td><td>6.5</td><td>6.4</td></tr></tbody>",
            2,
        ),
        mufg_html().replace("<td>6.7000</td>", "<td></td>"),
        mufg_html().replace("<td>6.7000</td>", "<td>not-a-number</td>"),
        mufg_html().replace("<td>6.7000</td>", "<td>0</td>"),
        mufg_html().replace("<td>6.7000</td>", "<td>inf</td>"),
        mufg_html().replace("Q4 2026", "Q3 2026"),
        mufg_html(updated="31 February 2026"),
        mufg_html(updated="03 July 2027"),
        mufg_html().replace("Latest FX forecast update: 03 July 2026", ""),
    ],
)
def test_parser_rejects_untrusted_content(html_text: str) -> None:
    with pytest.raises(ForecastSourceInvalidError):
        parse_mufg_forecast_html(html_text, RETRIEVED_AT)


def test_parser_requires_timezone_aware_retrieval_time() -> None:
    with pytest.raises(ForecastSourceInvalidError):
        parse_mufg_forecast_html(mufg_html(), RETRIEVED_AT.replace(tzinfo=None))


def test_parser_requires_at_least_two_future_points() -> None:
    retrieved_at = datetime(2027, 3, 31, 10, tzinfo=timezone.utc)

    with pytest.raises(ForecastSourceInvalidError):
        parse_mufg_forecast_html(mufg_html(updated="03 March 2027"), retrieved_at)


def test_provider_requests_only_the_fixed_official_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == MUFG_FORECAST_URL
        assert "fx-hedging-platform" in request.headers["User-Agent"]
        return httpx.Response(200, text=mufg_html())

    provider = MufgForecastProvider(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    result = provider.fetch(RETRIEVED_AT)

    assert result.institution == "MUFG"


@pytest.mark.parametrize("status", [404, 429, 503])
def test_provider_maps_http_failures_to_fetch_error(status: int) -> None:
    provider = MufgForecastProvider(
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, text="unavailable")
            )
        )
    )

    with pytest.raises(ForecastFetchError):
        provider.fetch(RETRIEVED_AT)


def test_provider_maps_transport_failure_to_fetch_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    provider = MufgForecastProvider(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(ForecastFetchError):
        provider.fetch(RETRIEVED_AT)
