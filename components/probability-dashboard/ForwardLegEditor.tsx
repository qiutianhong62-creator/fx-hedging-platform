import type { ForwardLegDraft } from "../../lib/analysis/probabilityDashboard.ts";

type ForwardLegEditorProps = {
  leg: ForwardLegDraft;
  index: number;
  canDelete: boolean;
  forwardLabel: string;
  onChange: (id: string, patch: Partial<ForwardLegDraft>) => void;
  onDelete: (id: string) => void;
};

function numericValue(value: number): number | "" {
  return Number.isNaN(value) ? "" : value;
}

export function ForwardLegEditor({
  leg,
  index,
  canDelete,
  forwardLabel,
  onChange,
  onDelete,
}: ForwardLegEditorProps) {
  return (
    <div className="forward-leg-row">
      <label className="dashboard-field">
        <span>第 {index + 1} 笔远期金额</span>
        <span className="dashboard-input">
          <input
            type="number"
            min="0"
            step="1000"
            inputMode="decimal"
            value={numericValue(leg.notionalUsd)}
            onChange={(event) =>
              onChange(leg.id, {
                notionalUsd:
                  event.target.value === ""
                    ? Number.NaN
                    : event.target.valueAsNumber,
              })
            }
            aria-label={`第 ${index + 1} 笔远期美元金额`}
          />
          <small>USD</small>
        </span>
      </label>
      <label className="dashboard-field">
        <span>真实远期{forwardLabel}报价</span>
        <span className="dashboard-input">
          <input
            type="number"
            min="0"
            step="0.0001"
            inputMode="decimal"
            value={numericValue(leg.forwardRate)}
            onChange={(event) =>
              onChange(leg.id, {
                forwardRate:
                  event.target.value === ""
                    ? Number.NaN
                    : event.target.valueAsNumber,
              })
            }
            aria-label={`第 ${index + 1} 笔远期${forwardLabel}报价`}
          />
          <small>CNY / USD</small>
        </span>
      </label>
      <button
        className="delete-leg-button"
        type="button"
        disabled={!canDelete}
        onClick={() => onDelete(leg.id)}
        aria-label={`删除第 ${index + 1} 笔远期`}
      >
        删除
      </button>
    </div>
  );
}
