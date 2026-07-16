export type OptionType = "call" | "put";
export type OptionPosition = "buy" | "sell";
export type ExposureDirection = "receivable" | "payable";

export type OptionInput = {
  notionalUsd: number;
  optionType: OptionType;
  position: OptionPosition;
  strikeRate: number;
  premiumRateCnyPerUsd: number;
  maturitySpot: number;
  exposureDirection: ExposureDirection;
};

export type OptionResult = {
  intrinsicValueCny: number;
  grossOptionPayoffCny: number;
  premiumCashflowCny: number;
  netOptionCashflowCny: number;
  baselineCashflowCny: number;
  finalCashflowCny: number;
  hedgingEffectCny: number;
  breakEvenRate: number;
};

export type OptionScenarioPoint = {
  spot: number;
  baselineCashflowCny: number;
  finalCashflowCny: number;
  netOptionCashflowCny: number;
};

export function validateOptionInput(input: OptionInput) {
  if (!Number.isFinite(input.notionalUsd) || input.notionalUsd < 0) {
    throw new Error("期权名义金额必须是非负数");
  }
  if (!Number.isFinite(input.strikeRate) || input.strikeRate <= 0) {
    throw new Error("期权执行价必须大于零");
  }
  if (
    !Number.isFinite(input.premiumRateCnyPerUsd) ||
    input.premiumRateCnyPerUsd < 0
  ) {
    throw new Error("期权费率必须是非负数");
  }
  if (!Number.isFinite(input.maturitySpot) || input.maturitySpot <= 0) {
    throw new Error("到期即期汇率必须大于零");
  }
}

export function calculateOption(input: OptionInput): OptionResult {
  validateOptionInput(input);

  const unitIntrinsic =
    input.optionType === "call"
      ? Math.max(input.maturitySpot - input.strikeRate, 0)
      : Math.max(input.strikeRate - input.maturitySpot, 0);
  const intrinsicValueCny = unitIntrinsic * input.notionalUsd;
  const positionSign = input.position === "buy" ? 1 : -1;
  const grossOptionPayoffCny = positionSign * intrinsicValueCny;
  const premiumCny = input.premiumRateCnyPerUsd * input.notionalUsd;
  const premiumCashflowCny = input.position === "buy" ? -premiumCny : premiumCny;
  const netOptionCashflowCny = grossOptionPayoffCny + premiumCashflowCny;
  const baselineCashflowCny = input.notionalUsd * input.maturitySpot;
  const finalCashflowCny =
    input.exposureDirection === "receivable"
      ? baselineCashflowCny + netOptionCashflowCny
      : baselineCashflowCny - netOptionCashflowCny;
  const breakEvenRate =
    input.optionType === "call"
      ? input.strikeRate + input.premiumRateCnyPerUsd
      : input.strikeRate - input.premiumRateCnyPerUsd;

  return {
    intrinsicValueCny,
    grossOptionPayoffCny,
    premiumCashflowCny,
    netOptionCashflowCny,
    baselineCashflowCny,
    finalCashflowCny,
    hedgingEffectCny: netOptionCashflowCny,
    breakEvenRate,
  };
}

export function buildOptionScenarios(
  input: OptionInput,
  minimumSpot: number,
  maximumSpot: number,
  steps = 31,
): OptionScenarioPoint[] {
  const count = Math.max(2, Math.round(steps));
  return Array.from({ length: count }, (_, index) => {
    const spot = minimumSpot + ((maximumSpot - minimumSpot) * index) / (count - 1);
    const result = calculateOption({ ...input, maturitySpot: spot });
    return {
      spot,
      baselineCashflowCny: result.baselineCashflowCny,
      finalCashflowCny: result.finalCashflowCny,
      netOptionCashflowCny: result.netOptionCashflowCny,
    };
  });
}

export function describeOptionRisk(input: OptionInput) {
  if (input.position === "buy") {
    return "期权买方拥有行权权利，最大期权头寸损失为已支付的期权费。";
  }
  if (input.optionType === "call") {
    return "卖出看涨期权会收取期权费，但当标的汇率持续上涨时可能产生很大的履约损失。";
  }
  return "卖出看跌期权会收取期权费，但当标的汇率大幅下跌时可能产生显著履约损失。";
}
