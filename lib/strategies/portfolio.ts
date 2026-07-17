import type { CompositeScenarioPoint } from "./types";

export type TradeProduct = "forward" | "option" | "swap" | "deposit";
export type Currency = "CNY" | "USD";
export type FxDirection = "buyUsd" | "sellUsd";
export type OptionKind = "call" | "put";
export type OptionPosition = "buy" | "sell";

export type PortfolioTrade = {
  id: string;
  name: string;
  enabled: boolean;
  product: TradeProduct;
  maturityDate: string;
  notional: number;
  notionalCurrency: Currency;
  direction: FxDirection;
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
    name: "1万元人民币远期购汇",
    enabled: true,
    product: "forward",
    maturityDate: "2026-12-31",
    notional: 10_000,
    notionalCurrency: "CNY",
    direction: "buyUsd",
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
    name: "卖出1万元名义金额看涨期权",
    enabled: true,
    product: "option",
    maturityDate: "2026-12-31",
    notional: 10_000,
    notionalCurrency: "CNY",
    direction: "buyUsd",
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
    enabled: true,
    product,
    maturityDate,
    notional: 10_000,
    notionalCurrency: "CNY",
    direction: "buyUsd",
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

export function usdNotional(trade: PortfolioTrade) {
  if (trade.notionalCurrency === "USD") return Math.max(0, trade.notional);
  const conversionRate = trade.product === "option" ? trade.strike : trade.contractRate;
  return Math.max(0, trade.notional) / safePositive(conversionRate, 1);
}

export function calculateTradePayoffCny(
  trade: PortfolioTrade,
  maturitySpot: number,
  context: PortfolioContext,
) {
  if (!trade.enabled || trade.maturityDate !== context.analysisDate) return 0;

  const spot = safePositive(maturitySpot, context.referenceSpot);
  const amount = Math.max(0, Number.isFinite(trade.notional) ? trade.notional : 0);

  if (trade.product === "forward" || trade.product === "swap") {
    const amountUsd = usdNotional(trade);
    const direction = trade.direction === "buyUsd" ? 1 : -1;
    return direction * (spot - safePositive(trade.contractRate, context.referenceSpot)) * amountUsd;
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
  if (trade.product === "forward") {
    return `${trade.direction === "buyUsd" ? "远期购汇" : "远期结汇"} · 锁定价 ${trade.contractRate.toFixed(4)}`;
  }
  if (trade.product === "swap") {
    return `${trade.direction === "buyUsd" ? "远端购汇" : "远端结汇"} · 远端价 ${trade.contractRate.toFixed(4)}`;
  }
  if (trade.product === "option") {
    return `${trade.optionPosition === "buy" ? "买入" : "卖出"}${trade.optionKind === "call" ? "看涨" : "看跌"} · 执行价 ${trade.strike.toFixed(4)}`;
  }
  return `${trade.notionalCurrency} 定存 · 税后年化 ${(trade.annualRate * (1 - trade.taxRate) * 100).toFixed(2)}%`;
}
