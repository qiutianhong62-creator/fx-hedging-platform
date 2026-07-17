export type OptionLegType =
  | "disabled"
  | "buyCall"
  | "sellCall"
  | "buyPut"
  | "sellPut";

export type CashflowTarget = "principal" | "interest";

export type OptionLeg = {
  target: CashflowTarget;
  type: OptionLegType;
  coverageRatio: number;
  strikeRate: number;
  premiumRate: number;
};

export type SettlementAllocation = {
  swapRatio: number;
  swapRate: number;
  forwardRatio: number;
  forwardRate: number;
};

export type MultiProductScheme = {
  id: string;
  name: string;
  enabled: boolean;
  color: string;
  depositRate: number;
  taxRate: number;
  principal: SettlementAllocation;
  interest: SettlementAllocation;
  optionLegs: [OptionLeg, OptionLeg];
};

export type MultiStrategyCommonInput = {
  initialCny: number;
  nearSpot: number;
  tenorDays: number;
  annualBasis: number;
  maturitySpot: number;
};

export type MultiSchemeResult = {
  totalCny: number;
  netGainCny: number;
  annualizedReturn: number;
  principalUsd: number;
  afterTaxInterestUsd: number;
  principalSpotRatio: number;
  interestSpotRatio: number;
  optionCashflowCny: number;
  status: "PASS" | "需复核";
  messages: string[];
};

const EPSILON = 1e-9;

export const optionLegLabels: Record<OptionLegType, string> = {
  disabled: "不启用",
  buyCall: "买入看涨",
  sellCall: "卖出看涨",
  buyPut: "买入看跌",
  sellPut: "卖出看跌",
};

function finite(value: number, fallback = 0) {
  return Number.isFinite(value) ? value : fallback;
}

function optionCashflow(
  leg: OptionLeg,
  principalUsd: number,
  interestUsd: number,
  maturitySpot: number,
) {
  if (leg.type === "disabled") return 0;
  const notional =
    (leg.target === "principal" ? principalUsd : interestUsd) *
    Math.max(0, finite(leg.coverageRatio));
  const strike = Math.max(EPSILON, finite(leg.strikeRate, 1));
  const premium = Math.max(0, finite(leg.premiumRate));
  const isCall = leg.type === "buyCall" || leg.type === "sellCall";
  const isBuy = leg.type === "buyCall" || leg.type === "buyPut";
  const intrinsic = isCall
    ? Math.max(maturitySpot - strike, 0)
    : Math.max(strike - maturitySpot, 0);
  return notional * (intrinsic * (isBuy ? 1 : -1) + premium * (isBuy ? -1 : 1));
}

function allocationCashflow(
  notionalUsd: number,
  allocation: SettlementAllocation,
  maturitySpot: number,
) {
  const swapRatio = Math.max(0, finite(allocation.swapRatio));
  const forwardRatio = Math.max(0, finite(allocation.forwardRatio));
  const spotRatio = 1 - swapRatio - forwardRatio;
  return {
    spotRatio,
    cashflowCny:
      notionalUsd *
      (swapRatio * Math.max(EPSILON, finite(allocation.swapRate, 1)) +
        forwardRatio * Math.max(EPSILON, finite(allocation.forwardRate, 1)) +
        Math.max(0, spotRatio) * maturitySpot),
  };
}

export function calculateMultiProductScheme(
  common: MultiStrategyCommonInput,
  scheme: MultiProductScheme,
): MultiSchemeResult {
  const messages: string[] = [];
  const initialCny = Math.max(0, finite(common.initialCny));
  const nearSpot = Math.max(EPSILON, finite(common.nearSpot, 1));
  const tenorDays = Math.max(0, finite(common.tenorDays));
  const annualBasis = Math.max(1, finite(common.annualBasis, 360));
  const maturitySpot = Math.max(EPSILON, finite(common.maturitySpot, nearSpot));
  const principalUsd = initialCny / nearSpot;
  const depositRate = Math.max(0, finite(scheme.depositRate));
  const taxRate = Math.min(1, Math.max(0, finite(scheme.taxRate)));
  const afterTaxInterestUsd =
    principalUsd * depositRate * (1 - taxRate) * (tenorDays / annualBasis);

  const principal = allocationCashflow(principalUsd, scheme.principal, maturitySpot);
  const interest = allocationCashflow(afterTaxInterestUsd, scheme.interest, maturitySpot);

  if (principal.spotRatio < -EPSILON) messages.push("本金的掉期与远期比例合计超过100%");
  if (interest.spotRatio < -EPSILON) messages.push("利息的掉期与远期比例合计超过100%");

  const openRatios = {
    principal: Math.max(0, principal.spotRatio),
    interest: Math.max(0, interest.spotRatio),
  };
  const coverage = {
    principal: { buyCall: 0, sellCall: 0, buyPut: 0, sellPut: 0 },
    interest: { buyCall: 0, sellCall: 0, buyPut: 0, sellPut: 0 },
  };

  let optionCashflowCny = 0;
  for (const leg of scheme.optionLegs) {
    optionCashflowCny += optionCashflow(
      leg,
      principalUsd,
      afterTaxInterestUsd,
      maturitySpot,
    );
    if (leg.type !== "disabled") {
      coverage[leg.target][leg.type] += Math.max(0, finite(leg.coverageRatio));
      if (leg.type === "buyCall" || leg.type === "sellPut") {
        messages.push(`${optionLegLabels[leg.type]}并非美元应收现金流的常规保护方向`);
      }
    }
  }

  for (const target of ["principal", "interest"] as const) {
    const directionalCoverage = Math.max(
      coverage[target].buyPut,
      coverage[target].sellCall,
      coverage[target].buyCall,
      coverage[target].sellPut,
    );
    if (directionalCoverage > openRatios[target] + EPSILON) {
      messages.push(`${target === "principal" ? "本金" : "利息"}期权名义覆盖超过开放现金流`);
    }
  }

  const totalCny = principal.cashflowCny + interest.cashflowCny + optionCashflowCny;
  const netGainCny = totalCny - initialCny;
  const annualizedReturn =
    initialCny > 0 && tenorDays > 0
      ? (netGainCny / initialCny) * (annualBasis / tenorDays)
      : 0;

  return {
    totalCny,
    netGainCny,
    annualizedReturn,
    principalUsd,
    afterTaxInterestUsd,
    principalSpotRatio: principal.spotRatio,
    interestSpotRatio: interest.spotRatio,
    optionCashflowCny,
    status: messages.length === 0 ? "PASS" : "需复核",
    messages,
  };
}

export function buildMultiProductScenarios(
  common: MultiStrategyCommonInput,
  scheme: MultiProductScheme,
  minimumSpot: number,
  maximumSpot: number,
  steps = 31,
) {
  const count = Math.max(2, Math.round(steps));
  return Array.from({ length: count }, (_, index) => {
    const spot = minimumSpot + ((maximumSpot - minimumSpot) * index) / (count - 1);
    const result = calculateMultiProductScheme(
      { ...common, maturitySpot: spot },
      scheme,
    );
    return {
      spot,
      incomeCny: result.totalCny,
      differenceCny: result.netGainCny,
    };
  });
}

