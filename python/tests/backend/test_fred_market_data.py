from datetime import date

import httpx
import pytest

from backend.market.errors import MarketDataFetchError, MarketDataInvalidError
from backend.market.fred import FredHistoryProvider, parse_fred_csv


def test_parse_fred_csv_cleans_missing_values_sorts_and_deduplicates() -> None:
    csv_text = """observation_date,DEXCHUS
2030-01-03,6.82
2030-01-01,6.80
2030-01-02,.
2030-01-03,6.83
2030-01-04,
"""

    observations = parse_fred_csv(csv_text)

    assert [(item.date.isoformat(), item.rate) for item in observations] == [
        ("2030-01-01", 6.80),
        ("2030-01-03", 6.83),
    ]


@pytest.mark.parametrize(
    "csv_text",
    [
        "date,value\n2030-01-01,6.8\n",
        "observation_date,DEXCHUS\nnot-a-date,6.8\n",
        "observation_date,DEXCHUS\n2030-01-01,nope\n",
        "observation_date,DEXCHUS\n2030-01-01,0\n",
        "observation_date,DEXCHUS\n2030-01-01,-1\n",
        "observation_date,DEXCHUS\n2030-01-01,inf\n",
    ],
)
def test_parse_fred_csv_rejects_invalid_upstream_content(csv_text: str) -> None:
    with pytest.raises(MarketDataInvalidError):
        parse_fred_csv(csv_text)


def test_fred_provider_builds_keyless_csv_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graph/fredgraph.csv"
        assert request.url.params["id"] == "DEXCHUS"
        assert request.url.params["cosd"] == "2029-01-01"
        assert request.url.params["coed"] == "2030-01-01"
        return httpx.Response(
            200,
            text="observation_date,DEXCHUS\n2029-12-31,6.80\n",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = FredHistoryProvider(http_client=client)

    observations = provider.fetch(date(2029, 1, 1), date(2030, 1, 1))

    assert observations[0].rate == 6.80


def test_fred_provider_maps_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    provider = FredHistoryProvider(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(MarketDataFetchError):
        provider.fetch(date(2029, 1, 1), date(2030, 1, 1))


def test_fred_provider_maps_non_success_status() -> None:
    provider = FredHistoryProvider(
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(503, text="unavailable")
            )
        )
    )

    with pytest.raises(MarketDataFetchError):
        provider.fetch(date(2029, 1, 1), date(2030, 1, 1))
