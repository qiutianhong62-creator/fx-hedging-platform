# Phase 6 Automatic No-Hedge Probability Design

## Goal

Add a new automatic no-hedge analysis endpoint. The user supplies only the
business exposure. The backend obtains the expected USD/CNY maturity spot from
the Phase 5 ING forecast service and the annualized historical volatility from
the Phase 4 FRED market-history service, then runs the existing Phase 3
lognormal probability calculation.

The existing manual probability endpoint remains unchanged. This gives the
product a dependable manual path for testing and comparison without silently
substituting assumptions when external data is unavailable.

## Scope

Phase 6 includes:

- one new automatic probability endpoint for `USD/CNY`;
- automatic ING expected-maturity-spot lookup for the user's maturity date;
- automatic FRED one-year historical-volatility lookup;
- reuse of the existing no-hedge amount, probability-range, and target
  probability calculations;
- traceable ING and FRED metadata in the automatic response;
- stable failures when either external data source is unavailable or invalid;
- automated tests with injected fake services and no live network calls.

Phase 6 does not include:

- additional forecasting institutions or institution weighting;
- implied volatility or a paid forward curve;
- hedge instruments or portfolio calculations;
- frontend work;
- background refresh jobs or a database;
- automatic fallback to guessed rates, default volatility, or user assumptions.

The forecast boundary remains provider-independent so additional institutions
can be added in a later phase without changing the probability engine.

## User Input

The new endpoint accepts the existing base exposure fields only:

```json
{
  "currency_pair": "USD/CNY",
  "exposure_type": "usd_receivable",
  "notional_usd": 1000000,
  "maturity_date": "2026-11-15",
  "target_cny": 6800000
}
```

`target_cny` remains optional. The automatic request does not accept
`assumed_expected_maturity_spot` or `assumed_annualized_volatility_pct`.

The existing manual endpoint continues to require both assumption fields and
keeps its current request and response contract.

## API

Add:

```text
POST /api/v1/analysis/no-hedge/automatic-probability
```

Keep unchanged:

```text
POST /api/v1/analysis/no-hedge/probability
```

The automatic response retains the familiar probability results:

- expected spot and expected CNY amount;
- central 50% spot and amount range;
- wide 90% spot and amount range;
- target-met and target-missed probabilities when a target is supplied.

It also returns `data_sources` containing the traceable Phase 5 forecast result
and Phase 4 market-history summary. This includes ING's update date, original
forecast points, interpolation anchors, FRED's observation date, volatility
window, retrieval time, and cache status.

The distribution metadata distinguishes the two paths:

```text
manual endpoint:    source_type = assumption,  is_market_forecast = false
automatic endpoint: source_type = market_data, is_market_forecast = true
```

Here `is_market_forecast` describes the expected maturity spot. The response
must continue to label the FRED volatility as historical rather than a future
volatility forecast.

## Architecture and Data Flow

```text
Exposure input
     |
     v
AutomaticNoHedgeProbabilityService
     |------------------------------|
     v                              v
MaturityForecastService       MarketHistoryService
ING expected spot             FRED historical volatility
     |                              |
     |------------------------------|
                    |
                    v
       existing probability calculation
                    |
                    v
 probability result + ING/FRED provenance
```

The route is thin. It validates the request and delegates to a new orchestration
service. That service:

1. requests the maturity-date estimate from `MaturityForecastService`;
2. requests the history summary from `MarketHistoryService`;
3. builds the existing internal probability input with the ING expected spot
   and FRED annualized historical volatility;
4. uses the forecast response's `valuation_date` as the probability horizon's
   valuation date;
5. calls the existing no-hedge probability calculation;
6. marks the distribution metadata as market-data driven;
7. attaches both source responses to the automatic result.

The amount and probability mathematics are not duplicated. Phase 6 only
orchestrates already tested components and adds accurate provenance metadata.

## Models

Add an automatic request model based on `AnalysisInput` without assumption
fields.

Widen `DistributionMetadata` so its source fields can accurately represent both
paths:

```text
source_type: assumption | market_data
is_market_forecast: boolean
```

The manual calculator continues to produce exactly `assumption` and `false`, so
its serialized response remains unchanged.

Add an automatic response model that extends the existing probability response
with:

```text
data_sources.forecast: MaturityForecastResponse
data_sources.market_history: MarketHistorySummaryResponse
```

The automatic orchestration service returns this specific response type.

## Failure Handling

No guessed or hidden fallback values are allowed.

- ING network, structure, freshness, cache, or horizon failures retain the
  existing stable forecast error codes and HTTP statuses.
- FRED network, freshness, cache, or data-quality failures retain the existing
  stable market-data error codes and HTTP statuses.
- Invalid exposure input retains the existing friendly validation response.
- Numerically invalid probability parameters retain the existing stable
  probability-calculation error.

The ING and FRED services may use only their already approved cache policies.
The automatic service does not add a second cache or weaken source freshness
rules.

## Testing

All automated tests use injected fake forecast and market-history services.
They never contact ING or FRED.

Tests cover:

- ING expected spot and FRED volatility are passed into the existing model;
- the forecast valuation date controls horizon length;
- expected CNY amount and target probabilities match the existing calculator;
- the automatic response marks the distribution as market-data driven;
- ING and FRED traceability metadata are returned;
- omitted `target_cny` still returns no target probability;
- forecast and market-data exceptions pass through unchanged;
- the manual endpoint retains its exact existing request and response behavior;
- the full backend regression suite remains green.

After automated tests pass, one manual live call verifies the complete chain:

```text
ING + FRED -> automatic endpoint -> amount ranges and target probability
```

## Success Criteria

Phase 6 is complete when a user can submit only an exposure, maturity date, and
optional target; receive a no-hedge probability analysis driven by current
approved ING and FRED data; inspect where both inputs came from; and receive a
clear error rather than a fabricated result when either source cannot provide
valid data.
