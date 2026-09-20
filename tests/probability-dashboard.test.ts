import assert from "node:assert/strict";
import test from "node:test";
import * as dashboard from "../lib/analysis/probabilityDashboard.ts";

import {
  allProbabilityRows,
  buildRequest,
  coverageSummary,
  formatProbability,
  mostLikelyInterval,
  selectCoreIntervals,
  validateDraft,
} from "../lib/analysis/probabilityDashboard.ts";

const draft = {
  exposureType: "usd_receivable" as const,
  notionalUsd: 1_000_000,
  maturityDate: "2099-12-31",
  targetCny: null,
  legs: [
    { id: "forward-1", notionalUsd: 300_000, forwardRate: 6.8 },
    { id: "forward-2", notionalUsd: 200_000, forwardRate: 6.75 },
  ],
};

test("payable request sends the budget and correct exposure direction", () => {
  const request = buildRequest({ ...draft, exposureType: "usd_payable" }, 7_000_000);
  assert.equal(request.exposure_type, "usd_payable");
  assert.equal(request.target_cny, 7_000_000);
  assert.deepEqual(request.forward_legs, [
    { notional_usd: 300_000, forward_rate: 6.8 },
    { notional_usd: 200_000, forward_rate: 6.75 },
  ]);
});

test("changing direction resets quotes and target but retains exposure and date", () => {
  for (const direction of ["usd_payable", "usd_receivable"] as const) {
    const next = dashboard.switchExposure({ ...draft, targetCny: 7_000_000 }, direction);
    assert.equal(next.exposureType, direction);
    assert.equal(next.notionalUsd, draft.notionalUsd);
    assert.equal(next.maturityDate, draft.maturityDate);
    assert.equal(next.targetCny, null);
    assert.equal(next.legs.length, 1);
    assert.ok(Number.isNaN(next.legs[0].notionalUsd));
    assert.ok(Number.isNaN(next.legs[0].forwardRate));
  }
});

test("payable validation describes an amount owed and a budget", () => {
  const errors = validateDraft({ ...draft, exposureType: "usd_payable", notionalUsd: 0, targetCny: -1 });
  assert.equal(errors.notionalUsd, "美元应付金额必须大于 0");
  assert.equal(errors.targetCny, "人民币预算上限必须大于 0");
});

test("empty quotes after a direction switch show zero coverage, not NaN", () => {
  const summary = coverageSummary(dashboard.switchExposure(draft, "usd_payable"));
  assert.equal(summary.totalForwardUsd, 0);
  assert.equal(summary.coverageRatio, 0);
  assert.equal(summary.unhedgedUsd, 1_000_000);
});

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

const intervalFixture = [
  {
    ...intervalsFixture[0],
    lower_spot: 6.55,
    upper_spot: 6.6,
    interval_probability: 0.1,
  },
  {
    ...intervalsFixture[1],
    lower_spot: 6.6,
    upper_spot: 6.65,
    interval_probability: 0.141,
  },
  {
    ...intervalsFixture[2],
    lower_spot: 6.65,
    upper_spot: 6.7,
    interval_probability: 0.12,
  },
];

const profileFixture = {
  core_lower_spot: intervalsFixture[0].lower_spot,
  core_upper_spot: intervalsFixture[19].upper_spot,
  core_probability: 0.98,
  bucket_count: 20,
  intervals: intervalsFixture,
  lower_tail: {
    direction: "below" as const,
    boundary_spot: intervalsFixture[0].lower_spot,
    probability: 0.01,
    no_hedge_amount_cny: 6_400_000,
    forward_strategy_amount_cny: 6_600_000,
  },
  upper_tail: {
    direction: "above" as const,
    boundary_spot: intervalsFixture[19].upper_spot,
    probability: 0.01,
    no_hedge_amount_cny: 7_200_000,
    forward_strategy_amount_cny: 7_000_000,
  },
};

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

test("most likely interval uses interval probability not an exact spot", () => {
  const mostLikely = mostLikelyInterval(intervalFixture);
  assert.equal(mostLikely.lower_spot, 6.6);
  assert.equal(mostLikely.upper_spot, 6.65);
  assert.equal(mostLikely.interval_probability, 0.141);
});

test("expanded rows include open tails and twenty core buckets", () => {
  const rows = allProbabilityRows(profileFixture);
  assert.equal(rows.length, 22);
  assert.equal(rows[0]?.kind, "lower_tail");
  assert.equal(rows.at(-1)?.kind, "upper_tail");
  assert.equal(rows[0]?.amountRangeKind, "boundary");
});
