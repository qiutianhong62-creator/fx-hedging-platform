export type AmountRange = {
  minimum_amount_cny: number;
  maximum_amount_cny: number;
};

export type ForwardProbabilityInterval = {
  lower_spot: number;
  upper_spot: number;
  interval_probability: number;
  probability_below_upper: number;
  probability_above_upper: number;
  no_hedge: AmountRange;
  forward_strategy: AmountRange;
  strategy_minus_no_hedge: AmountRange;
};

export type ForwardProbabilityRequest = {
  currency_pair: "USD/CNY";
  exposure_type: "usd_receivable";
  notional_usd: number;
  maturity_date: string;
  target_cny: number | null;
  forward_legs: Array<{ notional_usd: number; forward_rate: number }>;
};

export type ProbabilityRange = AmountRange & { probability: number };

export type TargetProbability = {
  target_cny: number;
  critical_spot: number | null;
  probability_met: number;
  probability_missed: number;
};

export type Coverage = {
  total_forward_notional_usd: number;
  coverage_ratio: number;
  unhedged_notional_usd: number;
  overhedged_notional_usd: number;
  status: "partial_hedge" | "full_hedge" | "over_hedged";
  warnings: Array<{ code: "over_hedged"; message: string }>;
};

export type StrategyResult = {
  expected_amount_cny: number;
  typical_range_50: ProbabilityRange;
  wide_range_90: ProbabilityRange;
  target_probability: TargetProbability | null;
};

export type ForecastSource = {
  institution: "ING" | "MUFG";
  matched_maturity_spot: number;
  weight: 0.5 | 1;
  matching: {
    method: "direct" | "interpolated";
    is_system_estimate: boolean;
    day_weight: number | null;
    anchors: Array<{
      source: "ING" | "MUFG" | "FRED";
      date: string;
      spot: number;
    }>;
  };
  source_updated_date: string;
  source_url: string;
  forecast_points: Array<{ date: string; spot: number }>;
  cache_status: "live_fetch" | "daily_cache" | "stale_fallback";
  fetched_at_utc: string;
  cache_age_hours: number;
  is_stale: boolean;
};

export type AutomaticForwardProbabilityResponse = {
  status: "calculated";
  quote_convention: "CNY per 1 USD";
  result_kind: "cny_proceeds";
  distribution: {
    model_type: "lognormal";
    source_type: "market_data";
    is_market_forecast: true;
    assumed_expected_maturity_spot: number;
    assumed_annualized_volatility_pct: number;
    horizon_days: number;
    typical_spot_range_50: {
      probability: number;
      lower_spot: number;
      upper_spot: number;
    };
    wide_spot_range_90: {
      probability: number;
      lower_spot: number;
      upper_spot: number;
    };
  };
  no_hedge: StrategyResult;
  forward_strategy: StrategyResult & { coverage: Coverage };
  comparison: {
    break_even_spot: number;
    probability_strategy_better: number;
    probability_no_hedge_better: number;
    wide_range_90_width: {
      no_hedge_width_cny: number;
      strategy_width_cny: number;
      strategy_minus_no_hedge_cny: number;
      change: "reduced" | "unchanged" | "increased";
    };
  };
  probability_profile: {
    core_lower_spot: number;
    core_upper_spot: number;
    core_probability: number;
    bucket_count: number;
    intervals: ForwardProbabilityInterval[];
    lower_tail: {
      direction: "below";
      boundary_spot: number;
      probability: number;
      no_hedge_amount_cny: number;
      forward_strategy_amount_cny: number;
    };
    upper_tail: {
      direction: "above";
      boundary_spot: number;
      probability: number;
      no_hedge_amount_cny: number;
      forward_strategy_amount_cny: number;
    };
  };
  data_sources: {
    forecast: {
      status: "available";
      currency_pair: "USD/CNY";
      quote_convention: "CNY per 1 USD";
      valuation_date: string;
      maturity_date: string;
      expected_maturity_spot: number;
      source_count: 1 | 2;
      aggregation_status:
        | "equal_weight_consensus"
        | "single_source_fallback";
      is_consensus_forecast: boolean;
      sources: ForecastSource[];
      unavailable_sources: Array<{
        institution: "ING" | "MUFG";
        reason_code:
          | "fetch_failed"
          | "source_invalid"
          | "source_stale"
          | "horizon_insufficient";
      }>;
      limitations: string[];
    };
    market_history: {
      status: "available";
      currency_pair: "USD/CNY";
      quote_convention: "CNY per 1 USD";
      market_reference: {
        spot: number;
        observation_date: string;
        is_live_quote: false;
      };
      historical_volatility: {
        annualized_volatility_pct: number;
        method: "daily_log_returns_sample_stddev";
        trading_days_per_year: 252;
        window: "1y";
        window_start: string;
        window_end: string;
        observation_count: number;
        return_count: number;
      };
      source: {
        provider: "FRED";
        series_id: "DEXCHUS";
        fetched_at_utc: string;
        cache_status: "live_fetch" | "daily_cache" | "stale_fallback";
        cache_age_hours: number;
        data_age_days: number;
        is_stale: boolean;
      };
    };
  };
  limitations: string[];
};

export class ForwardProbabilityApiError extends Error {
  readonly code: string;
  readonly fields: Array<{ field: string; message: string }>;
  readonly status: number | null;

  constructor(
    code: string,
    message: string,
    fields: Array<{ field: string; message: string }> = [],
    status: number | null = null,
  ) {
    super(message);
    this.name = "ForwardProbabilityApiError";
    this.code = code;
    this.fields = fields;
    this.status = status;
  }
}

type RequestOptions = {
  baseUrl?: string;
  fetcher?: typeof fetch;
};

const defaultBaseUrl =
  process.env.NEXT_PUBLIC_FX_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function requestForwardProbability(
  payload: ForwardProbabilityRequest,
  options: RequestOptions = {},
): Promise<AutomaticForwardProbabilityResponse> {
  const fetcher = options.fetcher ?? fetch;
  let response: Response;
  try {
    response = await fetcher(
      `${options.baseUrl ?? defaultBaseUrl}/api/v1/analysis/forward-strategy/automatic-probability`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
  } catch {
    throw new ForwardProbabilityApiError(
      "connection_error",
      "Python 服务未连接，请启动后端后重试。",
    );
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ForwardProbabilityApiError(
      error?.code ?? "analysis_error",
      error?.message ?? "分析失败，请稍后重试。",
      error?.fields ?? [],
      response.status,
    );
  }
  return body as AutomaticForwardProbabilityResponse;
}
