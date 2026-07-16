import type {
  HedgeProduct,
  ScenarioPoint,
  StrategyInput,
  StrategySummary,
} from "./types";

export function validateForwardInput(input: StrategyInput) {
  if (!Number.isFinite(input.exposureUsd) || input.exposureUsd < 0) {
    throw new Error("美元敞口必须是非负数");
  }
  if (!Number.isFinite(input.hedgeRatio) || input.hedgeRatio < 0 || input.hedgeRatio > 1) {
    throw new Error("套保比例必须位于0%至100%之间");
  }
  if (!Number.isFinite(input.forwardRate) || input.forwardRate <= 0) {
    throw new Error("远期汇率必须大于零");
  }
  if (!Number.isFinite(input.maturitySpot) || input.maturitySpot <= 0) {
    throw new Error("到期即期汇率必须大于零");
  }
}

export function calculateForward(input: StrategyInput): StrategySummary {
  validateForwardInput(input);
  const hedgedUsd = input.exposureUsd * input.hedgeRatio;
  const unhedgedUsd = input.exposureUsd - hedgedUsd;
  const totalIncomeCny = hedgedUsd * input.forwardRate + unhedgedUsd * input.maturitySpot;
  const unhedgedIncomeCny = input.exposureUsd * input.maturitySpot;
  return {
    hedgedUsd,
    unhedgedUsd,
    totalIncomeCny,
    unhedgedIncomeCny,
    differenceCny: totalIncomeCny - unhedgedIncomeCny,
  };
}

export function buildForwardScenarios(
  input: StrategyInput,
  minimum: number,
  maximum: number,
  steps = 15,
): ScenarioPoint[] {
  const count = Math.max(2, Math.round(steps));
  return Array.from({ length: count }, (_, index) => {
    const spot = minimum + ((maximum - minimum) * index) / (count - 1);
    const result = calculateForward({ ...input, maturitySpot: spot });
    return {
      spot,
      hedgedIncomeCny: result.totalIncomeCny,
      unhedgedIncomeCny: result.unhedgedIncomeCny,
      differenceCny: result.differenceCny,
    };
  });
}

export const forwardProduct: HedgeProduct = {
  id: "forward",
  name: "远期结汇",
  calculate: calculateForward,
  scenarios: buildForwardScenarios,
};
