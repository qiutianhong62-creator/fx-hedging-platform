import type {
  ForwardProbabilityInterval,
  ForwardProbabilityRequest,
} from "../api/forwardProbability.ts";

export type ForwardLegDraft = {
  id: string;
  notionalUsd: number;
  forwardRate: number;
};

export type AnalysisDraft = {
  notionalUsd: number;
  maturityDate: string;
  targetCny: number | null;
  legs: ForwardLegDraft[];
};

export type DraftErrors = Partial<
  Record<"notionalUsd" | "maturityDate" | "legs" | "targetCny", string>
>;

export function createInitialDraft(): AnalysisDraft {
  return {
    notionalUsd: 0,
    maturityDate: "",
    targetCny: null,
    legs: [{ id: "forward-1", notionalUsd: 0, forwardRate: 0 }],
  };
}

export function coverageSummary(draft: AnalysisDraft) {
  const totalForwardUsd = draft.legs.reduce(
    (total, leg) => total + leg.notionalUsd,
    0,
  );
  const coverageRatio =
    draft.notionalUsd > 0 ? totalForwardUsd / draft.notionalUsd : 0;
  const overhedgedUsd = Math.max(0, totalForwardUsd - draft.notionalUsd);
  return {
    totalForwardUsd,
    coverageRatio,
    unhedgedUsd: Math.max(0, draft.notionalUsd - totalForwardUsd),
    overhedgedUsd,
    status:
      overhedgedUsd > 0
        ? ("over_hedged" as const)
        : totalForwardUsd === draft.notionalUsd
          ? ("full_hedge" as const)
          : ("partial_hedge" as const),
  };
}

export function validateDraft(draft: AnalysisDraft): DraftErrors {
  const errors: DraftErrors = {};
  if (!Number.isFinite(draft.notionalUsd) || draft.notionalUsd <= 0) {
    errors.notionalUsd = "美元应收金额必须大于 0";
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const maturity = draft.maturityDate
    ? new Date(`${draft.maturityDate}T00:00:00`)
    : null;
  if (!maturity || Number.isNaN(maturity.valueOf()) || maturity <= today) {
    errors.maturityDate = "请选择晚于今天的分析到期日";
  }
  if (draft.legs.length === 0) {
    errors.legs = "请至少保留一笔远期交易";
  } else if (
    draft.legs.some(
      (leg) =>
        !Number.isFinite(leg.notionalUsd) ||
        leg.notionalUsd <= 0 ||
        !Number.isFinite(leg.forwardRate) ||
        leg.forwardRate <= 0,
    )
  ) {
    errors.legs = "每笔远期的金额和报价都必须大于 0";
  }
  if (
    draft.targetCny !== null &&
    (!Number.isFinite(draft.targetCny) || draft.targetCny <= 0)
  ) {
    errors.targetCny = "目标人民币金额必须大于 0";
  }
  return errors;
}

export function buildRequest(
  draft: AnalysisDraft,
  targetCny: number | null,
): ForwardProbabilityRequest {
  return {
    currency_pair: "USD/CNY",
    exposure_type: "usd_receivable",
    notional_usd: draft.notionalUsd,
    maturity_date: draft.maturityDate,
    target_cny: targetCny,
    forward_legs: draft.legs.map((leg) => ({
      notional_usd: leg.notionalUsd,
      forward_rate: leg.forwardRate,
    })),
  };
}

export function selectCoreIntervals(
  intervals: ForwardProbabilityInterval[],
  count = 8,
): ForwardProbabilityInterval[] {
  return intervals
    .map((interval, index) => ({ interval, index }))
    .sort(
      (left, right) =>
        right.interval.interval_probability -
          left.interval.interval_probability || left.index - right.index,
    )
    .slice(0, count)
    .map(({ interval }) => interval)
    .sort((left, right) => left.lower_spot - right.lower_spot);
}

export function formatProbability(value: number): string {
  if (value > 0 && value < 0.001) return "<0.1%";
  return `${(value * 100).toFixed(1)}%`;
}

export function formatCnyWan(value: number): string {
  return `${(value / 10_000).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} 万元`;
}

export function formatFullCny(value: number): string {
  return `${value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} 元`;
}

export function formatUsd(value: number): string {
  return `${value.toLocaleString("en-US", {
    maximumFractionDigits: 2,
  })} 美元`;
}

export function formatSpot(value: number): string {
  return value.toFixed(4);
}
