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
