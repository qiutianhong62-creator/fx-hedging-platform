import type { TargetProbability, ResultKind } from "../../lib/api/forwardProbability.ts";
import { exposureCopy } from "../../lib/analysis/exposurePresentation.ts";
import {
  formatProbability,
  formatSpot,
} from "../../lib/analysis/probabilityDashboard.ts";

type TargetAnalysisPanelProps = {
  targetCny: number | null;
  resultKind: ResultKind;
  disabled: boolean;
  loading: boolean;
  error: string | null;
  noHedge: TargetProbability | null;
  strategy: TargetProbability | null;
  onTargetChange: (value: number | null) => void;
  onSubmit: () => void;
};

function criticalSpotText(result: TargetProbability, kind: ResultKind): string {
  if (result.critical_spot !== null) {
    return `对应的临界到期汇率约为 ${formatSpot(result.critical_spot)}`;
  }
  return result.probability_met === 1
    ? `在本模型分布下始终${exposureCopy(kind).met}`
    : `在本模型分布下始终${exposureCopy(kind).missed}`;
}

export function TargetAnalysisPanel({
  targetCny,
  resultKind,
  disabled,
  loading,
  error,
  noHedge,
  strategy,
  onTargetChange,
  onSubmit,
}: TargetAnalysisPanelProps) {
  const copy = exposureCopy(resultKind);
  const percentagePointChange =
    noHedge && strategy
      ? (strategy.probability_met - noHedge.probability_met) * 100
      : null;

  return (
    <section className="result-section target-analysis" aria-labelledby="target-title">
      <div className="result-heading">
        <div>
          <p className="section-kicker">第二步 · 自定目标</p>
          <h2 id="target-title">{copy.targetTitle}</h2>
          <p>先查看分析结果，再填写{copy.target}；系统会更新分析结果及达标概率。</p>
          {resultKind === "cny_cost" && <p>付款成本不超过预算（包含相等）即为达标。</p>}
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
          <span>{copy.target}</span>
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
        <button className="primary-button target-button" type="submit" disabled={loading || disabled}>
          {loading ? "正在计算达标概率…" : "计算达标概率"}
        </button>
      </form>
      {disabled && !loading && <p className="stale-notice">请先重新分析当前条件，再计算达标概率。</p>}
      {error && <p className="field-error target-error" role="alert">{error}</p>}

      {noHedge && strategy && percentagePointChange !== null && (
        <div className="target-result-grid">
          <article>
            <span>不套保{copy.met}</span>
            <strong>{formatProbability(noHedge.probability_met)}</strong>
            <small>{criticalSpotText(noHedge, resultKind)}</small>
            <small>{copy.missed}：{formatProbability(noHedge.probability_missed)}</small>
          </article>
          <article>
            <span>远期策略{copy.met}</span>
            <strong>{formatProbability(strategy.probability_met)}</strong>
            <small>{criticalSpotText(strategy, resultKind)}</small>
            <small>{copy.missed}：{formatProbability(strategy.probability_missed)}</small>
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
