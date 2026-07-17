import type { CompositeScenarioPoint } from "./types";

export type TradeProduct = "forward" | "option" | "swap" | "deposit";
export type Currency = "CNY" | "USD";
export type FxDirection = "buyUsd" | "sellUsd";
export type OptionKind = "call" | "put";
export type OptionPosition = "buy" | "sell";

export type PortfolioTrade = {
  id: string;
  name: string;
  nameManuallyEdited: boolean;
  enabled: boolean;
  product: TradeProduct;
  nearDate: string;
  maturityDate: string;
  notional: number;
  notionalCurrency: Currency;
  notionalSourceTradeId: string | null;
  direction: FxDirection;
  nearRate: number;
  contractRate: number;
  optionKind: OptionKind;
  optionPosition: OptionPosition;
  strike: number;
  premium: number;
  annualRate: number;
  taxRate: number;
  dayCount: number;
};

export type PortfolioContext = {
  analysisDate: string;
  referenceSpot: number;
};

export const productLabels: Record<TradeProduct, string> = {
  forward: "远期",
  option: "期权",
  swap: "掉期",
  deposit: "定存",
};

export const productColors: Record<TradeProduct, string> = {
  forward: "#1f6fb2",
  option: "#8a63b8",
  swap: "#e5824f",
  deposit: "#087f73",
};

export const defaultPortfolioTrades: PortfolioTrade[] = [
  {
    id: "trade-forward-example",
    name: "远期1",
    nameManuallyEdited: false,
    enabled: true,
    product: "forward",
    nearDate: "2026-07-17",
    maturityDate: "2026-12-31",
    notional: 10_000,
    notionalCurrency: "CNY",
    notionalSourceTradeId: null,
    direction: "buyUsd",
    nearRate: 6.80,
    contractRate: 6.74,
    optionKind: "call",
    optionPosition: "buy",
    strike: 6.9,
    premium: 0.025,
    annualRate: 0.03,
    taxRate: 0.1,
    dayCount: 180,
  },
  {
    id: "trade-option-example",
    name: "期权1",
    nameManuallyEdited: false,
    enabled: true,
    product: "option",
    nearDate: "2026-07-17",
    maturityDate: "2026-12-31",
    notional: 10_000,
    notionalCurrency: "CNY",
    notionalSourceTradeId: null,
    direction: "buyUsd",
    nearRate: 6.80,
    contractRate: 6.74,
    optionKind: "call",
    optionPosition: "sell",
    strike: 6.9,
    premium: 0.025,
    annualRate: 0.03,
    taxRate: 0.1,
    dayCount: 180,
  },
];

export function createPortfolioTrade(product: TradeProduct, id: string, maturityDate: string): PortfolioTrade {
  const label = productLabels[product];
  return {
    id,
    name: `新增${label}交易`,
    nameManuallyEdited: false,
    enabled: true,
    product,
    nearDate: "2026-07-17",
    maturityDate,
    notional: 10_000,
    notionalCurrency: "CNY",
    notionalSourceTradeId: null,
    direction: "buyUsd",
    nearRate: 6.80,
    contractRate: 6.74,
    optionKind: "call",
    optionPosition: "buy",
    strike: 6.9,
    premium: 0.025,
    annualRate: 0.03,
    taxRate: 0.1,
    dayCount: 180,
  };
}

function safePositive(value: number, fallback: number) {
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function isPositive(value: number) {
  return Number.isFinite(value) && value > 0;
}

function isNonNegative(value: number) {
  return Number.isFinite(value) && value >= 0;
}

export function normalizeAutomaticTradeNames(trades: PortfolioTrade[]) {
  const counts: Record<TradeProduct, number> = { forward: 0, option: 0, swap: 0, deposit: 0 };
  return trades.map((trade) => {
    counts[trade.product] += 1;
    if (trade.nameManuallyEdited) return trade;
    return { ...trade, name: `${productLabels[trade.product]}${counts[trade.product]}` };
  });
}

export function differenceInDays(startDate: string, endDate: string) {
  const start = Date.parse(`${startDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 0;
  return Math.max(0, Math.round((end - start) / 86_400_000));
}

export function calculateDepositInterest(trade: PortfolioTrade) {
  const principal = isPositive(trade.notional) ? trade.notional : 0;
  const annualRate = isNonNegative(trade.annualRate) ? trade.annualRate : 0;
  const taxRate = isNonNegative(trade.taxRate) ? Math.min(1, trade.taxRate) : 0;
  const dayCount = isPositive(trade.dayCount) ? trade.dayCount : 0;
  const grossInterest = principal * annualRate * dayCount / 360;
  const taxAmount = grossInterest * taxRate;
  const netInterest = grossInterest - taxAmount;
  return {
    currency: trade.notionalCurrency,
    grossInterest,
    taxAmount,
    netInterest,
    netAnnualRate: annualRate * (1 - taxRate),
    valid: trade.product === "deposit"
      && isPositive(trade.notional)
      && isNonNegative(trade.annualRate)
      && isNonNegative(trade.taxRate)
      && isPositive(trade.dayCount),
  };
}

export function resolveLinkedNotionals(trades: PortfolioTrade[]) {
  const byId = new Map(trades.map((trade) => [trade.id, trade]));
  return trades.map((trade) => {
    if (trade.product !== "forward" || !trade.notionalSourceTradeId) return trade;
    const source = byId.get(trade.notionalSourceTradeId);
    if (!source || source.product !== "deposit") {
      return { ...trade, notional: Number.NaN };
    }
    const interest = calculateDepositInterest(source);
    return {
      ...trade,
      notional: interest.valid ? interest.netInterest : Number.NaN,
      notionalCurrency: source.notionalCurrency,
    };
  });
}

export function usdNotional(trade: PortfolioTrade) {
  if (!isPositive(trade.notional)) return 0;
  if (trade.notionalCurrency === "USD") return trade.notional;
  const conversionRate = trade.product === "option"
    ? trade.strike
    : trade.product === "swap"
      ? trade.nearRate
      : trade.contractRate;
  return Math.max(0, trade.notional) / safePositive(conversionRate, 1);
}

export function cnyEquivalentNotional(trade: PortfolioTrade, context: PortfolioContext) {
  if (!isPositive(trade.notional)) return 0;
  return trade.notionalCurrency === "CNY"
    ? trade.notional
    : trade.notional * safePositive(context.referenceSpot, 0);
}

export function tradeHasRequiredInputs(trade: PortfolioTrade) {
  if (!isPositive(trade.notional)) return false;
  if (trade.product === "forward") return isPositive(trade.contractRate);
  if (trade.product === "swap") {
    return isPositive(trade.nearRate)
      && isPositive(trade.contractRate)
      && differenceInDays(trade.nearDate, trade.maturityDate) > 0;
  }
  if (trade.product === "option") {
    return isPositive(trade.strike) && isNonNegative(trade.premium);
  }
  return isNonNegative(trade.annualRate)
    && isNonNegative(trade.taxRate)
    && isPositive(trade.dayCount);
}

export function tradeMatchesAnalysis(trade: PortfolioTrade, context: PortfolioContext) {
  return trade.enabled
    && tradeHasRequiredInputs(trade)
    && trade.maturityDate === context.analysisDate;
}

export function calculateSwapQuote(trade: PortfolioTrade) {
  const nearValid = isPositive(trade.notional) && isPositive(trade.nearRate);
  const farRateValid = isPositive(trade.contractRate);
  const amountUsd = usdNotional(trade);
  const nearRate = safePositive(trade.nearRate, 0);
  const farRate = safePositive(trade.contractRate, 0);
  const tenorDays = differenceInDays(trade.nearDate, trade.maturityDate);
  const dateValid = tenorDays > 0;
  const direction = trade.direction === "buyUsd" ? 1 : -1;
  const annualizedReturn = nearRate > 0 && tenorDays > 0
    ? direction * ((farRate - nearRate) / nearRate) * (360 / tenorDays)
    : Number.NaN;
  return {
    amountUsd,
    nearCny: amountUsd * nearRate,
    farCny: amountUsd * farRate,
    swapPoints: (farRate - nearRate) * 10_000,
    tenorDays,
    annualizedReturn,
    nearValid,
    farRateValid,
    dateValid,
    valid: trade.product === "swap" && nearValid && farRateValid && dateValid,
  };
}

export function calculateTradePayoffCny(
  trade: PortfolioTrade,
  maturitySpot: number,
  context: PortfolioContext,
) {
  if (!tradeMatchesAnalysis(trade, context)) return 0;

  const spot = safePositive(maturitySpot, context.referenceSpot);
  const amount = Math.max(0, Number.isFinite(trade.notional) ? trade.notional : 0);

  if (trade.product === "forward") {
    const amountUsd = usdNotional(trade);
    const direction = trade.direction === "buyUsd" ? 1 : -1;
    return direction * (spot - safePositive(trade.contractRate, context.referenceSpot)) * amountUsd;
  }

  if (trade.product === "swap") {
    const amountUsd = usdNotional(trade);
    const nearDirection = trade.direction === "buyUsd" ? 1 : -1;
    const nearPayoff = nearDirection
      * (context.referenceSpot - safePositive(trade.nearRate, context.referenceSpot))
      * amountUsd;
    const farDirection = -nearDirection;
    const farPayoff = farDirection
      * (spot - safePositive(trade.contractRate, context.referenceSpot))
      * amountUsd;
    return nearPayoff + farPayoff;
  }

  if (trade.product === "option") {
    const amountUsd = usdNotional(trade);
    const strike = safePositive(trade.strike, context.referenceSpot);
    const intrinsic = trade.optionKind === "call"
      ? Math.max(spot - strike, 0)
      : Math.max(strike - spot, 0);
    const position = trade.optionPosition === "buy" ? 1 : -1;
    const premium = Math.max(0, Number.isFinite(trade.premium) ? trade.premium : 0);
    return position * intrinsic * amountUsd - position * premium * amountUsd;
  }

  const rate = Math.max(0, Number.isFinite(trade.annualRate) ? trade.annualRate : 0);
  const tax = Math.min(1, Math.max(0, Number.isFinite(trade.taxRate) ? trade.taxRate : 0));
  const days = Math.max(0, Number.isFinite(trade.dayCount) ? trade.dayCount : 0);
  const netYield = rate * (1 - tax) * days / 360;
  if (trade.notionalCurrency === "CNY") return amount * netYield;

  return amount * ((1 + netYield) * spot - context.referenceSpot);
}

export function calculatePortfolioPayoffCny(
  trades: PortfolioTrade[],
  maturitySpot: number,
  context: PortfolioContext,
) {
  return trades.reduce(
    (total, trade) => total + calculateTradePayoffCny(trade, maturitySpot, context),
    0,
  );
}

export function calculateTradeReferenceProfitCny(
  trade: PortfolioTrade,
  maturitySpot: number,
  context: PortfolioContext,
) {
  if (!tradeMatchesAnalysis(trade, context)) return 0;
  if (trade.product === "swap") {
    const direction = trade.direction === "buyUsd" ? 1 : -1;
    return direction * (trade.contractRate - trade.nearRate) * usdNotional(trade);
  }
  if (trade.product === "deposit") {
    const interest = calculateDepositInterest(trade);
    return trade.notionalCurrency === "CNY"
      ? interest.netInterest
      : interest.netInterest * safePositive(maturitySpot, context.referenceSpot);
  }
  return calculateTradePayoffCny(trade, maturitySpot, context);
}

export function calculatePortfolioReferenceProfitCny(
  trades: PortfolioTrade[],
  maturitySpot: number,
  context: PortfolioContext,
) {
  return trades.reduce(
    (total, trade) => total + calculateTradeReferenceProfitCny(trade, maturitySpot, context),
    0,
  );
}

export function buildPortfolioScenarios(
  trades: PortfolioTrade[],
  context: PortfolioContext,
  minimum: number,
  maximum: number,
  steps = 41,
): CompositeScenarioPoint[] {
  const count = Math.max(2, steps);
  return Array.from({ length: count }, (_, index) => {
    const spot = minimum + ((maximum - minimum) * index) / (count - 1);
    const incomeCny = calculatePortfolioPayoffCny(trades, spot, context);
    return { spot, incomeCny, differenceCny: incomeCny };
  });
}

export function tradeDescription(trade: PortfolioTrade) {
  const formatRate = (value: number) => isPositive(value) ? value.toFixed(4) : "待输入";
  if (trade.product === "forward") {
    return `${trade.direction === "buyUsd" ? "远期购汇" : "远期结汇"} · 锁定价 ${formatRate(trade.contractRate)}`;
  }
  if (trade.product === "swap") {
    const near = trade.direction === "buyUsd" ? "近端购汇" : "近端结汇";
    const far = trade.direction === "buyUsd" ? "远端结汇" : "远端购汇";
    return `${near} ${formatRate(trade.nearRate)} → ${far} ${formatRate(trade.contractRate)}`;
  }
  if (trade.product === "option") {
    return `${trade.optionPosition === "buy" ? "买入" : "卖出"}${trade.optionKind === "call" ? "看涨" : "看跌"} · 执行价 ${formatRate(trade.strike)}`;
  }
  const annualRate = Number.isFinite(trade.annualRate) ? trade.annualRate : 0;
  const taxRate = Number.isFinite(trade.taxRate) ? trade.taxRate : 0;
  return `${trade.notionalCurrency} 定存 · 税后年化 ${(annualRate * (1 - taxRate) * 100).toFixed(2)}%`;
}
