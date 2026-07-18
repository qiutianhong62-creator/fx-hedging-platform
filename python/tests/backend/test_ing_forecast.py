from datetime import date, datetime, timezone

import httpx
import pytest

from backend.forecast.errors import ForecastFetchError, ForecastSourceInvalidError
from backend.forecast.ing import (
    ING_FORECAST_URL,
    IngForecastProvider,
    parse_ing_forecast_html,
    parse_quarter_label,
)


RETRIEVED_AT = datetime(2026, 7, 18, 10, tzinfo=timezone.utc)


def ing_html(*, updated: str = "16 July", pair: str = "USD/CNY") -> str:
    return f"""
    <div id="growth-gdp">
      <h2>Growth (GDP)</h2><p>Last updated: 1 July</p>
      <table><thead><tr><th>Asia</th><th></th><th>3Q26F</th></tr></thead>
      <tbody><tr><td>China</td><td>{pair}</td><td>99</td></tr></tbody></table>
    </div>
    <div id="fx">
      <h2>FX</h2><p>Last updated: {updated}</p>
      <table>
        <thead><tr><th>Asia (eop)</th><th></th><th>3Q26F</th><th>4Q26F</th><th>1Q27F</th></tr></thead>
        <tbody><tr><td>China</td><td>{pair}</td><td>6.74</td><td>6.70</td><td>6.68</td></tr></tbody>
      </table>
    </div>
    """


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("1Q27F", date(2027, 3, 31)),
        ("2Q27F", date(2027, 6, 30)),
        ("3Q27F", date(2027, 9, 30)),
        ("4Q27F", date(2027, 12, 31)),
    ],
)
def test_parse_quarter_label_uses_natural_quarter_end(
    label: str,
    expected: date,
) -> None:
    assert parse_quarter_label(label) == expected


def test_parser_reads_only_fx_usd_cny_and_resolves_update_year() -> None:
    snapshot = parse_ing_forecast_html(ing_html(), RETRIEVED_AT)

    assert snapshot.institution == "ING"
    assert snapshot.currency_pair == "USD/CNY"
    assert snapshot.source_url == ING_FORECAST_URL
    assert snapshot.source_updated_date == date(2026, 7, 16)
    assert [(item.date, item.spot) for item in snapshot.points] == [
        (date(2026, 9, 30), 6.74),
        (date(2026, 12, 31), 6.70),
        (date(2027, 3, 31), 6.68),
    ]


def test_parser_resolves_december_update_to_previous_year_in_january() -> None:
    retrieved = datetime(2026, 1, 5, tzinfo=timezone.utc)

    snapshot = parse_ing_forecast_html(
        ing_html(updated="20 December"),
        retrieved,
    )

    assert snapshot.source_updated_date == date(2025, 12, 20)


@pytest.mark.parametrize(
    "html_text",
    [
        "<div id='growth-gdp'><p>Last updated: 16 July</p></div>",
        ing_html(pair="CNY/USD"),
        ing_html().replace("6.74", "0"),
        ing_html().replace("3Q26F", "Q3-2026"),
        ing_html().replace("<td>6.70</td>", "<td>not-a-number</td>"),
    ],
)
def test_parser_rejects_missing_or_invalid_fx_content(html_text: str) -> None:
    with pytest.raises(ForecastSourceInvalidError):
        parse_ing_forecast_html(html_text, RETRIEVED_AT)


def test_provider_requests_only_the_fixed_official_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == ING_FORECAST_URL
        assert "fx-hedging-platform" in request.headers["User-Agent"]
        return httpx.Response(200, text=ing_html())

    provider = IngForecastProvider(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    snapshot = provider.fetch(RETRIEVED_AT)

    assert snapshot.points[0].spot == 6.74


@pytest.mark.parametrize("status", [404, 429, 503])
def test_provider_maps_http_failures_to_fetch_error(status: int) -> None:
    provider = IngForecastProvider(
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, text="unavailable")
            )
        )
    )

    with pytest.raises(ForecastFetchError):
        provider.fetch(RETRIEVED_AT)
