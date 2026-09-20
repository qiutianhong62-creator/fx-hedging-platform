import type { AutomaticForwardProbabilityResponse } from "../../lib/api/forwardProbability.ts";
import { exposureCopy } from "../../lib/analysis/exposurePresentation.ts";
import {
  formatCnyWan,
  formatFullCny,
  formatProbability,
  formatSpot,
  mostLikelyInterval,
} from "../../lib/analysis/probabilityDashboard.ts";

type ResponseProps = { response: AutomaticForwardProbabilityResponse };

function AmountRange({
  minimum,
  maximum,
}: {
  minimum: number;
  maximum: number;
}) {
  return (
    <span title={`${formatFullCny(minimum)} 至 ${formatFullCny(maximum)}`}>
      {formatCnyWan(minimum)} – {formatCnyWan(maximum)}
    </span>
  );
}

export function AnalysisSummary({ response }: ResponseProps) {
  const copy = exposureCopy(response.result_kind);
  const likely = mostLikelyInterval(response.probability_profile.intervals);

  return (
    <section className="result-section" aria-labelledby="analysis-summary-title">
      <div className="result-heading">
        <div>
          <p className="section-kicker">结果摘要</p>
          <h2 id="analysis-summary-title">先看最重要的数字</h2>
        </div>
        <span className="model-chip">
          预测期限 {response.distribution.horizon_days} 天
        </span>
      </div>

      <div className="analysis-summary-grid">
        <article className="summary-card summary-card-accent">
          <span>模型预计到期汇率</span>
          <strong>{formatSpot(response.distribution.assumed_expected_maturity_spot)}</strong>
          <small>人民币 / 1 美元</small>
        </article>
        <article className="summary-card">
          <span>最可能的汇率区间</span>
          <strong>{formatSpot(likely.lower_spot)} – {formatSpot(likely.upper_spot)}</strong>
          <small>区间发生概率 {formatProbability(likely.interval_probability)}</small>
        </article>
        <article className="summary-card">
          <span>不套保预计{copy.amount}</span>
          <strong title={formatFullCny(response.no_hedge.expected_amount_cny)}>
            {formatCnyWan(response.no_hedge.expected_amount_cny)}
          </strong>
          <small>随到期汇率变动</small>
        </article>
        <article className="summary-card summary-card-accent">
          <span>远期策略预计{copy.amount}</span>
          <strong title={formatFullCny(response.forward_strategy.expected_amount_cny)}>
            {formatCnyWan(response.forward_strategy.expected_amount_cny)}
          </strong>
          <small>当前覆盖比例 {formatProbability(response.forward_strategy.coverage.coverage_ratio)}</small>
        </article>
      </div>

      <div className="range-comparison-grid">
        <article>
          <h3>常见范围（50% 概率）</h3>
          <p><span>不套保</span><AmountRange minimum={response.no_hedge.typical_range_50.minimum_amount_cny} maximum={response.no_hedge.typical_range_50.maximum_amount_cny} /></p>
          <p><span>远期策略</span><AmountRange minimum={response.forward_strategy.typical_range_50.minimum_amount_cny} maximum={response.forward_strategy.typical_range_50.maximum_amount_cny} /></p>
        </article>
        <article>
          <h3>较宽范围（90% 概率）</h3>
          <p><span>不套保</span><AmountRange minimum={response.no_hedge.wide_range_90.minimum_amount_cny} maximum={response.no_hedge.wide_range_90.maximum_amount_cny} /></p>
          <p><span>远期策略</span><AmountRange minimum={response.forward_strategy.wide_range_90.minimum_amount_cny} maximum={response.forward_strategy.wide_range_90.maximum_amount_cny} /></p>
        </article>
      </div>
    </section>
  );
}
