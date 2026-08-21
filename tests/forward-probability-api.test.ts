import assert from "node:assert/strict";
import test from "node:test";

import {
  ForwardProbabilityApiError,
  requestForwardProbability,
  type ForwardProbabilityRequest,
} from "../lib/api/forwardProbability.ts";

const request: ForwardProbabilityRequest = {
  currency_pair: "USD/CNY",
  exposure_type: "usd_receivable",
  notional_usd: 1_000_000,
  maturity_date: "2026-12-31",
  target_cny: null,
  forward_legs: [
    { notional_usd: 300_000, forward_rate: 6.8 },
    { notional_usd: 200_000, forward_rate: 6.75 },
  ],
};

test("posts the exact automatic probability request", async () => {
  let capturedUrl = "";
  let capturedInit: RequestInit | undefined;
  const fetcher: typeof fetch = async (input, init) => {
    capturedUrl = String(input);
    capturedInit = init;
    return new Response(JSON.stringify({ status: "calculated" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  await requestForwardProbability(request, {
    baseUrl: "http://127.0.0.1:8000",
    fetcher,
  });

  assert.equal(
    capturedUrl,
    "http://127.0.0.1:8000/api/v1/analysis/forward-strategy/automatic-probability",
  );
  assert.equal(capturedInit?.method, "POST");
  assert.deepEqual(JSON.parse(String(capturedInit?.body)), request);
});

test("normalizes FastAPI field errors", async () => {
  const fetcher: typeof fetch = async () =>
    new Response(
      JSON.stringify({
        error: {
          code: "validation_error",
          message: "输入内容有误",
          fields: [
            { field: "forward_rate", message: "远期汇率必须大于 0" },
          ],
        },
      }),
      { status: 422, headers: { "content-type": "application/json" } },
    );

  await assert.rejects(
    requestForwardProbability(request, { fetcher }),
    (error: unknown) => {
      assert.ok(error instanceof ForwardProbabilityApiError);
      assert.equal(error.code, "validation_error");
      assert.equal(error.fields[0]?.field, "forward_rate");
      return true;
    },
  );
});

test("maps a rejected fetch to connection_error", async () => {
  const fetcher: typeof fetch = async () => {
    throw new TypeError("fetch failed");
  };

  await assert.rejects(
    requestForwardProbability(request, { fetcher }),
    (error: unknown) => {
      assert.ok(error instanceof ForwardProbabilityApiError);
      assert.equal(error.code, "connection_error");
      assert.match(error.message, /Python 服务未连接/);
      return true;
    },
  );
});
