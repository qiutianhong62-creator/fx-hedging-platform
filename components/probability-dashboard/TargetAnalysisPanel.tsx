import type { TargetProbability } from "../../lib/api/forwardProbability.ts";
import {
  formatProbability,
  formatSpot,
} from "../../lib/analysis/probabilityDashboard.ts";

type TargetAnalysisPanelProps = {
  targetCny: number | null;
  loading: boolean;
  error: string | null;
  noHedge: TargetProbability | null;
  strategy: TargetProbability | null;
  onTargetChange: (value: number | null) => void;
  onSubmit: () => void;
};

function criticalSpotText(result: TargetProbability): string {
  if (result.critical_spot !== null) {
    return `对应的临界到期汇率约为 ${formatSpot(result.critical_spot)}`;
  }
  return result.probability_met === 1
    ? "在本模型分布下始终达到目标"
    : "在本模型分布下始终未达到目标";
}

export function TargetAnalysisPanel({
  targetCny,
  loading,
  error,
  noHedge,
  strategy,
  onTargetChange,
  onSubmit,
}: TargetAnalysisPanelProps) {
  const percentagePointChange =
    noHedge && strategy
      ? (strategy.probability_met - noHedge.probability_met) * 100
      : null;

  return (
    <section className="result-section target-analysis" aria-labelledby="target-title">
      <div className="result-heading">
        <div>
          <p className="section-kicker">第二步 · 自定目标</p>
          <h2 id="target-title">你的收款目标有多大概率实现</h2>
          <p>先查看分析结果，再填写目标人民币金额；系统会用同一组市场数据重新计算达标概率。</p>
        </div>
      </div>
      <form
        className="target-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <label className="dashboard-field">
          <span>目标人民币金额</span>
          <span className="dashboard-input">
            <input
              type="number"
              min="0"
              step="10000"
              inputMode="decimal"
              value={targetCny ?? ""}
              onChange={(event) =>
                onTargetChange(
                  event.target.value === "" ? null : event.target.valueAsNumber,
                )
              }
            />
            <small>CNY</small>
          </span>
        </label>
        <button className="primary-button target-button" type="submit" disabled={loading}>
          {loading ? "正在计算达标概率…" : "计算达标概率"}
        </button>
      </form>
      {error && <p className="field-error target-error" role="alert">{error}</p>}

      {noHedge && strategy && percentagePointChange !== null && (
        <div className="target-result-grid">
          <article>
            <span>不套保达到目标</span>
            <strong>{formatProbability(noHedge.probability_met)}</strong>
            <small>{criticalSpotText(noHedge)}</small>
          </article>
          <article>
            <span>远期策略达到目标</span>
            <strong>{formatProbability(strategy.probability_met)}</strong>
            <small>{criticalSpotText(strategy)}</small>
          </article>
          <article className={percentagePointChange >= 0 ? "target-change-positive" : "target-change-negative"}>
            <span>远期策略相对变化</span>
            <strong>{percentagePointChange >= 0 ? "+" : ""}{percentagePointChange.toFixed(1)} 个百分点</strong>
            <small>远期策略概率 − 不套保概率</small>
          </article>
        </div>
      )}
    </section>
  );
}
