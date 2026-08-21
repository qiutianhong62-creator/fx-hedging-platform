import type { AutomaticForwardProbabilityResponse } from "../../lib/api/forwardProbability.ts";

type ResponseProps = { response: AutomaticForwardProbabilityResponse };

export function RiskNotices({ response }: ResponseProps) {
  const forecast = response.data_sources.forecast;
  const history = response.data_sources.market_history;
  const dynamicNotices: string[] = [];

  if (forecast.aggregation_status === "single_source_fallback") {
    dynamicNotices.push("本次只有一家机构预测可用，综合结果的代表性较弱。");
  }
  if (forecast.sources.some((source) => source.is_stale) || history.source.is_stale) {
    dynamicNotices.push("本次使用了备用缓存，数据可能不是最新发布版本。");
  }
  if (response.forward_strategy.coverage.status === "over_hedged") {
    dynamicNotices.push("远期总金额超过美元应收敞口，策略包含过度套保风险。");
  }

  const notices = Array.from(
    new Set([
      ...response.limitations,
      ...forecast.limitations,
      "机构预测可能与实际汇率明显不同。",
      "历史波动率不保证代表未来波动。",
      "结果不构成银行报价、交易建议或收益保证。",
      ...dynamicNotices,
    ]),
  );

  return (
    <section className="result-section risk-notices" aria-labelledby="risk-title">
      <div className="result-heading">
        <div>
          <p className="section-kicker">使用前须知</p>
          <h2 id="risk-title">怎样理解这些概率结果</h2>
        </div>
      </div>
      <ul className="risk-notice-list">
        {notices.map((notice) => <li key={notice}>{notice}</li>)}
      </ul>
    </section>
  );
}
