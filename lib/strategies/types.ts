export type StrategyInput = {
  exposureUsd: number;
  hedgeRatio: number;
  forwardRate: number;
  maturitySpot: number;
};

export type StrategySummary = {
  hedgedUsd: number;
  unhedgedUsd: number;
  totalIncomeCny: number;
  unhedgedIncomeCny: number;
  differenceCny: number;
};

export type ScenarioPoint = {
  spot: number;
  hedgedIncomeCny: number;
  unhedgedIncomeCny: number;
  differenceCny: number;
};

export type HedgeProduct = {
  id: string;
  name: string;
  calculate: (input: StrategyInput) => StrategySummary;
  scenarios: (
    input: StrategyInput,
    minimum: number,
    maximum: number,
    steps?: number,
  ) => ScenarioPoint[];
};

export type ProductId =
  | "forward"
  | "option"
  | "future"
  | "swap"
  | "money-market";

export type StrategyLeg = {
  id: string;
  productId: ProductId;
  label: string;
  allocationRatio: number;
  parameters: Record<string, number>;
};

export type CompositeStrategy = {
  id: string;
  name: string;
  description: string;
  legs: StrategyLeg[];
};

export type CompositeStrategyResult = {
  coveredRatio: number;
  uncoveredRatio: number;
  coveredUsd: number;
  uncoveredUsd: number;
  productIncomeCny: number;
  uncoveredIncomeCny: number;
  totalIncomeCny: number;
  baselineIncomeCny: number;
  differenceCny: number;
  upfrontCostCny: number;
};

export type CompositeScenarioPoint = {
  spot: number;
  incomeCny: number;
  differenceCny: number;
};

export type StrategyComparisonResult = {
  strategy: CompositeStrategy;
  selected: CompositeStrategyResult;
  scenarios: CompositeScenarioPoint[];
  worstIncomeCny: number;
  bestIncomeCny: number;
  incomeRangeCny: number;
};
