import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRequest,
  coverageSummary,
  formatProbability,
  selectCoreIntervals,
  validateDraft,
} from "../lib/analysis/probabilityDashboard.ts";

const draft = {
  notionalUsd: 1_000_000,
  maturityDate: "2099-12-31",
  targetCny: null,
  legs: [
    { id: "forward-1", notionalUsd: 300_000, forwardRate: 6.8 },
    { id: "forward-2", notionalUsd: 200_000, forwardRate: 6.75 },
  ],
};

const intervalsFixture = Array.from({ length: 20 }, (_, index) => ({
  lower_spot: 6.4 + index * 0.01,
  upper_spot: 6.41 + index * 0.01,
  interval_probability: index / 100,
  probability_below_upper: index / 20,
  probability_above_upper: 1 - index / 20,
  no_hedge: { minimum_amount_cny: 1, maximum_amount_cny: 2 },
  forward_strategy: { minimum_amount_cny: 2, maximum_amount_cny: 3 },
  strategy_minus_no_hedge: {
    minimum_amount_cny: 1,
    maximum_amount_cny: 1,
  },
}));

test("builds the fixed USD receivable request without a target", () => {
  assert.deepEqual(buildRequest(draft, null), {
    currency_pair: "USD/CNY",
    exposure_type: "usd_receivable",
    notional_usd: 1_000_000,
    maturity_date: "2099-12-31",
    target_cny: null,
    forward_legs: [
      { notional_usd: 300_000, forward_rate: 6.8 },
      { notional_usd: 200_000, forward_rate: 6.75 },
    ],
  });
});

test("coverage allows and reports over-hedging", () => {
  const summary = coverageSummary({
    ...draft,
    legs: [
      { id: "forward-1", notionalUsd: 1_200_000, forwardRate: 6.8 },
    ],
  });
  assert.equal(summary.status, "over_hedged");
  assert.equal(summary.overhedgedUsd, 200_000);
  assert.equal(summary.coverageRatio, 1.2);
});

test("validation rejects invalid fields but not over-hedging", () => {
  assert.deepEqual(validateDraft({ ...draft, notionalUsd: 0 }), {
    notionalUsd: "美元应收金额必须大于 0",
  });
  assert.deepEqual(
    validateDraft({
      ...draft,
      legs: [
        { id: "forward-1", notionalUsd: 1_200_000, forwardRate: 6.8 },
      ],
    }),
    {},
  );
});

test("selects eight highest probabilities then restores spot order", () => {
  const selected = selectCoreIntervals(intervalsFixture, 8);
  assert.deepEqual(
    selected.map((item) => item.lower_spot),
    intervalsFixture.slice(12).map((item) => item.lower_spot),
  );
});

test("validation identifies missing date and invalid leg values", () => {
  assert.deepEqual(
    validateDraft({
      ...draft,
      maturityDate: "",
      legs: [{ id: "forward-1", notionalUsd: 0, forwardRate: 0 }],
    }),
    {
      maturityDate: "请选择晚于今天的分析到期日",
      legs: "每笔远期的金额和报价都必须大于 0",
    },
  );
});

test("probability ties keep original bucket order", () => {
  const tied = intervalsFixture.map((item) => ({
    ...item,
    interval_probability: 0.05,
  }));
  assert.deepEqual(
    selectCoreIntervals(tied, 8).map((item) => item.lower_spot),
    tied.slice(0, 8).map((item) => item.lower_spot),
  );
});

test("tiny nonzero probability is not formatted as zero", () => {
  assert.equal(formatProbability(0.0002), "<0.1%");
});
