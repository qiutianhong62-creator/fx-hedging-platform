import type {
  AnalysisDraft,
  DraftErrors,
  ForwardLegDraft,
  coverageSummary,
} from "../../lib/analysis/probabilityDashboard.ts";
import { formatProbability, formatUsd } from "../../lib/analysis/probabilityDashboard.ts";
import { ForwardLegEditor } from "./ForwardLegEditor";
import { exposureCopy } from "../../lib/analysis/exposurePresentation.ts";

type AnalysisInputPanelProps = {
  draft: AnalysisDraft;
  errors: DraftErrors;
  loading: boolean;
  stale: boolean;
  coverage: ReturnType<typeof coverageSummary>;
  onDraftChange: (patch: Partial<AnalysisDraft>) => void;
  onLegChange: (id: string, patch: Partial<ForwardLegDraft>) => void;
  onAddLeg: () => void;
  onDeleteLeg: (id: string) => void;
  onSubmit: () => void;
};

function numericValue(value: number): number | "" {
  return Number.isNaN(value) ? "" : value;
}

export function AnalysisInputPanel({
  draft,
  errors,
  loading,
  stale,
  coverage,
  onDraftChange,
  onLegChange,
  onAddLeg,
  onDeleteLeg,
  onSubmit,
}: AnalysisInputPanelProps) {
  const copy = exposureCopy(draft.exposureType === "usd_payable" ? "cny_cost" : "cny_proceeds");
  return (
    <section className="analysis-input-card" aria-labelledby="input-title">
      <div className="card-heading">
        <div>
          <p className="section-kicker">第一步 · 输入真实条件</p>
          <h2 id="input-title">你的{copy.exposure}与远期报价</h2>
        </div>
        <span className="scope-chip">USD/CNY · {copy.exposure} · 同一到期日</span>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <div className="analysis-input-grid">
          <label className="dashboard-field">
            <span>{copy.exposure}金额</span>
            <span className="dashboard-input">
              <input
                type="number"
                min="0"
                step="1000"
                inputMode="decimal"
                value={numericValue(draft.notionalUsd)}
                onChange={(event) =>
                  onDraftChange({
                    notionalUsd:
                      event.target.value === ""
                        ? Number.NaN
                        : event.target.valueAsNumber,
                  })
                }
                aria-describedby={errors.notionalUsd ? "notional-error" : undefined}
              />
              <small>USD</small>
            </span>
            {errors.notionalUsd && (
              <small className="field-error" id="notional-error">
                {errors.notionalUsd}
              </small>
            )}
          </label>
          <label className="dashboard-field">
            <span>分析到期日</span>
            <span className="dashboard-input">
              <input
                type="date"
                value={draft.maturityDate}
                onChange={(event) =>
                  onDraftChange({ maturityDate: event.target.value })
                }
                aria-describedby={errors.maturityDate ? "maturity-error" : undefined}
              />
            </span>
            {errors.maturityDate && (
              <small className="field-error" id="maturity-error">
                {errors.maturityDate}
              </small>
            )}
          </label>
        </div>

        <div className="forward-section-heading">
          <div>
            <p className="section-kicker">远期{copy.forward}交易</p>
            <h3>输入银行给你的真实报价</h3>
          </div>
          <button className="secondary-button" type="button" onClick={onAddLeg}>
            ＋ 添加一笔远期
          </button>
        </div>

        <div className="forward-leg-list">
          {draft.legs.map((leg, index) => (
            <ForwardLegEditor
              key={leg.id}
              leg={leg}
              index={index}
              canDelete={draft.legs.length > 1}
              forwardLabel={copy.forward}
              onChange={onLegChange}
              onDelete={onDeleteLeg}
            />
          ))}
        </div>
        {errors.legs && <p className="field-error">{errors.legs}</p>}

        <div className="coverage-strip" aria-label="套保覆盖情况">
          <div>
            <span>远期总金额</span>
            <strong>{formatUsd(coverage.totalForwardUsd)}</strong>
          </div>
          <div>
            <span>套保覆盖比例</span>
            <strong>{formatProbability(coverage.coverageRatio)}</strong>
          </div>
          <div>
            <span>未套保金额</span>
            <strong>{formatUsd(coverage.unhedgedUsd)}</strong>
          </div>
        </div>

        {coverage.status === "over_hedged" && (
          <p className="overhedge-warning" role="alert">
            当前远期金额超过{copy.exposure}金额，多出 {formatUsd(coverage.overhedgedUsd)}。
            系统允许继续分析，但结果会包含过度套保风险。
          </p>
        )}
        {stale && (
          <p className="stale-notice">
            输入已经改变，下面保留的是上一次结果。请重新分析以更新结果。
          </p>
        )}

        <button className="primary-button" type="submit" disabled={loading}>
          {loading ? "正在连接市场数据…" : "开始概率分析"}
        </button>
      </form>
    </section>
  );
}
