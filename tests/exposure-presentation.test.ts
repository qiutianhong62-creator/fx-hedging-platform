import assert from "node:assert/strict";
import test from "node:test";
import { improvementRange, signedCnyRange } from "../lib/analysis/exposurePresentation.ts";

test("payable savings reverse and reorder the backend cost difference", () => {
  assert.deepEqual(improvementRange({ minimum_amount_cny: -200_000, maximum_amount_cny: -100_000 }, "cny_cost"),
    { minimum_amount_cny: 100_000, maximum_amount_cny: 200_000 });
  assert.deepEqual(improvementRange({ minimum_amount_cny: -100_000, maximum_amount_cny: 50_000 }, "cny_cost"),
    { minimum_amount_cny: -50_000, maximum_amount_cny: 100_000 });
});

test("receivable retains its increased-income difference", () => {
  assert.deepEqual(improvementRange({ minimum_amount_cny: -20, maximum_amount_cny: 10 }, "cny_proceeds"),
    { minimum_amount_cny: -20, maximum_amount_cny: 10 });
});

test("ranges retain loss signs, increasing order, and mixed signs", () => {
  assert.equal(signedCnyRange(-200_000, -100_000), "-20.00 万元 – -10.00 万元");
  assert.equal(signedCnyRange(-50_000, 100_000), "-5.00 万元 – +10.00 万元");
  assert.equal(signedCnyRange(0, 0), "0.00 万元");
  assert.equal(signedCnyRange(-0, -0), "0.00 万元");
  assert.equal(signedCnyRange(100_000, 100_000), "+10.00 万元");
});
