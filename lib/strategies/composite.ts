import type {
  CompositeScenarioPoint,
  CompositeStrategy,
  CompositeStrategyResult,
  StrategyComparisonResult,
} from "./types";

const EPSILON = 1e-9;

export function createForwardStrategy(
  id: string,
  name: string,
  hedgeRatio: number,
  forwardRate: number,
  description: string,
): CompositeStrategy {
  return {
    id,
    name,
    description,
    legs:
      hedgeRatio > 0
        ? [
            {
              id: `${id}-forward`,
              productId: "forward",
              label: "远期结汇",
              allocationRatio: hedgeRatio,
              parameters: { forwardRate },
            },
          ]
        : [],
  };
}

export function validateCompositeStrategy(strategy: CompositeStrategy) {
  let coveredRatio = 0;
  for (const leg of strategy.legs) {
    if (!Number.isFinite(leg.allocationRatio) || leg.allocationRatio < 0) {
      throw new Error(`${leg.label}的配置比例必须是非负数`);
    }
    coveredRatio += leg.allocationRatio;
    if (leg.productId === "forward") {
      const rate = leg.parameters.forwardRate;
      if (!Number.isFinite(rate) || rate <= 0) {
        throw new Error(`${leg.label}的远期汇率必须大于零`);
      }
    } else {
      throw new Error(`产品 ${leg.productId} 尚未接入计算引擎`);
    }
  }
  if (coveredRatio > 1 + EPSILON) {
    throw new Error("组合策略的总覆盖比例不能超过100%：请检查是否重复或过度套保");
  }
  return Math.min(1, coveredRatio);
}

export function calculateCompositeStrategy(
  exposureUsd: number,
  maturitySpot: number,
  strategy: CompositeStrategy,
): CompositeStrategyResult {
  if (!Number.isFinite(exposureUsd) || exposureUsd < 0) {
    throw new Error("美元敞口必须是非负数");
  }
  if (!Number.isFinite(maturitySpot) || maturitySpot <= 0) {
    throw new Error("到期即期汇率必须大于零");
  }

  const coveredRatio = validateCompositeStrategy(strategy);
  let productIncomeCny = 0;
  let upfrontCostCny = 0;

  for (const leg of strategy.legs) {
    const notionalUsd = exposureUsd * leg.allocationRatio;
    if (leg.productId === "forward") {
      productIncomeCny += notionalUsd * leg.parameters.forwardRate;
    }
    upfrontCostCny += leg.parameters.upfrontCostCny ?? 0;
  }

  const uncoveredRatio = Math.max(0, 1 - coveredRatio);
  const coveredUsd = exposureUsd * coveredRatio;
  const uncoveredUsd = exposureUsd * uncoveredRatio;
  const uncoveredIncomeCny = uncoveredUsd * maturitySpot;
  const totalIncomeCny = productIncomeCny + uncoveredIncomeCny - upfrontCostCny;
  const baselineIncomeCny = exposureUsd * maturitySpot;

  return {
    coveredRatio,
    uncoveredRatio,
    coveredUsd,
    uncoveredUsd,
    productIncomeCny,
    uncoveredIncomeCny,
    totalIncomeCny,
    baselineIncomeCny,
    differenceCny: totalIncomeCny - baselineIncomeCny,
    upfrontCostCny,
  };
}

export function buildCompositeScenarios(
  exposureUsd: number,
  strategy: CompositeStrategy,
  minimumSpot: number,
  maximumSpot: number,
  steps = 21,
): CompositeScenarioPoint[] {
  const count = Math.max(2, Math.round(steps));
  return Array.from({ length: count }, (_, index) => {
    const spot = minimumSpot + ((maximumSpot - minimumSpot) * index) / (count - 1);
    const result = calculateCompositeStrategy(exposureUsd, spot, strategy);
    return {
      spot,
      incomeCny: result.totalIncomeCny,
      differenceCny: result.differenceCny,
    };
  });
}

export function compareCompositeStrategy(
  exposureUsd: number,
  maturitySpot: number,
  strategy: CompositeStrategy,
  minimumSpot: number,
  maximumSpot: number,
): StrategyComparisonResult {
  const selected = calculateCompositeStrategy(exposureUsd, maturitySpot, strategy);
  const scenarios = buildCompositeScenarios(
    exposureUsd,
    strategy,
    minimumSpot,
    maximumSpot,
  );
  const incomes = scenarios.map((point) => point.incomeCny);
  const worstIncomeCny = Math.min(...incomes);
  const bestIncomeCny = Math.max(...incomes);
  return {
    strategy,
    selected,
    scenarios,
    worstIncomeCny,
    bestIncomeCny,
    incomeRangeCny: bestIncomeCny - worstIncomeCny,
  };
}
